package chunker

import (
	"encoding/json"
	"fmt"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strings"
	"unicode/utf8"
)

const DefaultChunkSize = 500

var blankLinePattern = regexp.MustCompile(`\n\s*\n`)

type DocumentPayload struct {
	DocumentID      int64
	KnowledgeBaseID int64
	Scope           string
	TeamID          *int64
}

type Result struct {
	ChunkedPath      string
	SourceParsedPath string
	ChunkCount       int
	ChunkSize        int
}

type parsedDocumentPayload struct {
	DocumentID       int64  `json:"document_id"`
	KnowledgeBaseID  int64  `json:"knowledge_base_id"`
	Scope            string `json:"scope"`
	TeamID           *int64 `json:"team_id"`
	OriginalFilename string `json:"original_filename"`
	Content          string `json:"content"`
}

func ChunkDocumentFromParsedResult(document DocumentPayload, parsedRoot string, chunksRoot string) (Result, error) {
	parsedRelativePath, err := buildParsedRelativePath(
		document.Scope,
		document.KnowledgeBaseID,
		document.DocumentID,
		document.TeamID,
	)
	if err != nil {
		return Result{}, err
	}

	parsedSource := filepath.Join(parsedRoot, filepath.FromSlash(parsedRelativePath))
	body, err := os.ReadFile(parsedSource)
	if err != nil {
		if os.IsNotExist(err) {
			return Result{}, fmt.Errorf("parsed document result does not exist")
		}
		return Result{}, fmt.Errorf("failed to read parsed document result: %w", err)
	}

	var parsedPayload parsedDocumentPayload
	if err := json.Unmarshal(body, &parsedPayload); err != nil {
		return Result{}, fmt.Errorf("parsed document result is not valid JSON")
	}
	if parsedPayload.Content == "" {
		return Result{}, fmt.Errorf("parsed document result does not contain text content")
	}

	chunks, err := SplitTextIntoChunks(parsedPayload.Content, DefaultChunkSize)
	if err != nil {
		return Result{}, err
	}

	chunkRelativePath, err := buildChunkRelativePath(
		document.Scope,
		document.KnowledgeBaseID,
		document.DocumentID,
		document.TeamID,
	)
	if err != nil {
		return Result{}, err
	}

	destination := filepath.Join(chunksRoot, filepath.FromSlash(chunkRelativePath))
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return Result{}, fmt.Errorf("failed to prepare chunk output directory: %w", err)
	}

	payload := map[string]any{
		"document_id":        document.DocumentID,
		"knowledge_base_id":  document.KnowledgeBaseID,
		"scope":              document.Scope,
		"team_id":            document.TeamID,
		"original_filename":  parsedPayload.OriginalFilename,
		"source_parsed_path": parsedRelativePath,
		"chunk_size":         DefaultChunkSize,
		"chunk_count":        len(chunks),
		"chunks":             buildChunkEntries(document.DocumentID, chunks),
	}

	encoded, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return Result{}, fmt.Errorf("failed to encode chunk payload: %w", err)
	}
	encoded = append(encoded, '\n')

	if err := os.WriteFile(destination, encoded, 0o644); err != nil {
		return Result{}, fmt.Errorf("failed to write chunk result: %w", err)
	}

	return Result{
		ChunkedPath:      chunkRelativePath,
		SourceParsedPath: parsedRelativePath,
		ChunkCount:       len(chunks),
		ChunkSize:        DefaultChunkSize,
	}, nil
}

func SplitTextIntoChunks(text string, chunkSize int) ([]string, error) {
	normalized := strings.TrimSpace(strings.ReplaceAll(strings.ReplaceAll(text, "\r\n", "\n"), "\r", "\n"))
	if normalized == "" {
		return nil, fmt.Errorf("parsed document contains no content to chunk")
	}
	if chunkSize <= 0 {
		return nil, fmt.Errorf("chunk_size must be greater than zero")
	}

	rawBlocks := blankLinePattern.Split(normalized, -1)
	blocks := make([]string, 0, len(rawBlocks))
	for _, block := range rawBlocks {
		trimmed := strings.TrimSpace(block)
		if trimmed != "" {
			blocks = append(blocks, trimmed)
		}
	}

	chunks := make([]string, 0, len(blocks))
	currentParts := make([]string, 0, 4)
	currentLength := 0

	for _, block := range blocks {
		blockLength := utf8.RuneCountInString(block)
		if blockLength > chunkSize {
			if len(currentParts) > 0 {
				chunks = append(chunks, strings.Join(currentParts, "\n\n"))
				currentParts = currentParts[:0]
				currentLength = 0
			}

			for _, piece := range splitLongBlock(block, chunkSize) {
				if piece != "" {
					chunks = append(chunks, piece)
				}
			}
			continue
		}

		separatorLength := 0
		if len(currentParts) > 0 {
			separatorLength = 2
		}
		tentativeLength := currentLength + separatorLength + blockLength
		if tentativeLength <= chunkSize {
			currentParts = append(currentParts, block)
			currentLength = tentativeLength
			continue
		}

		chunks = append(chunks, strings.Join(currentParts, "\n\n"))
		currentParts = []string{block}
		currentLength = blockLength
	}

	if len(currentParts) > 0 {
		chunks = append(chunks, strings.Join(currentParts, "\n\n"))
	}

	if len(chunks) == 0 {
		return nil, fmt.Errorf("parsed document contains no content to chunk")
	}
	return chunks, nil
}

func buildChunkEntries(documentID int64, chunks []string) []map[string]any {
	entries := make([]map[string]any, 0, len(chunks))
	for index, text := range chunks {
		entries = append(entries, map[string]any{
			"index":      index,
			"chunk_id":   fmt.Sprintf("%d:%d", documentID, index),
			"char_count": utf8.RuneCountInString(text),
			"text":       text,
		})
	}
	return entries
}

func splitLongBlock(block string, chunkSize int) []string {
	runes := []rune(block)
	pieces := make([]string, 0, (len(runes)/chunkSize)+1)
	for start := 0; start < len(runes); start += chunkSize {
		end := start + chunkSize
		if end > len(runes) {
			end = len(runes)
		}
		piece := strings.TrimSpace(string(runes[start:end]))
		if piece != "" {
			pieces = append(pieces, piece)
		}
	}
	return pieces
}

func buildParsedRelativePath(scope string, knowledgeBaseID int64, documentID int64, teamID *int64) (string, error) {
	filename := fmt.Sprintf("document_%d.json", documentID)

	switch scope {
	case "personal":
		return path.Join(
			"personal",
			fmt.Sprintf("knowledge_base_%d", knowledgeBaseID),
			filename,
		), nil
	case "team":
		if teamID == nil {
			return "", fmt.Errorf("team_id is required for team document chunking")
		}
		return path.Join(
			"team",
			fmt.Sprintf("team_%d", *teamID),
			fmt.Sprintf("knowledge_base_%d", knowledgeBaseID),
			filename,
		), nil
	default:
		return "", fmt.Errorf("unsupported knowledge base scope: %s", scope)
	}
}

func buildChunkRelativePath(scope string, knowledgeBaseID int64, documentID int64, teamID *int64) (string, error) {
	filename := fmt.Sprintf("document_%d.json", documentID)

	switch scope {
	case "personal":
		return path.Join(
			"personal",
			fmt.Sprintf("knowledge_base_%d", knowledgeBaseID),
			filename,
		), nil
	case "team":
		if teamID == nil {
			return "", fmt.Errorf("team_id is required for team document chunking")
		}
		return path.Join(
			"team",
			fmt.Sprintf("team_%d", *teamID),
			fmt.Sprintf("knowledge_base_%d", knowledgeBaseID),
			filename,
		), nil
	default:
		return "", fmt.Errorf("unsupported knowledge base scope: %s", scope)
	}
}
