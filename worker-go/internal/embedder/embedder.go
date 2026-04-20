package embedder

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strings"
)

const (
	EmbeddingDimension = 128
	EmbeddingScheme    = "hashed_bow_v1"
)

var tokenPattern = regexp.MustCompile(`[A-Za-z0-9]+|[\x{4e00}-\x{9fff}]`)

type DocumentPayload struct {
	DocumentID      int64
	KnowledgeBaseID int64
	Scope           string
	TeamID          *int64
}

type Result struct {
	IndexPath          string
	EmbeddedChunkCount int
	EmbeddingDimension int
	SourceChunkPath    string
}

type chunkPayload struct {
	DocumentID      int64        `json:"document_id"`
	KnowledgeBaseID int64        `json:"knowledge_base_id"`
	Scope           string       `json:"scope"`
	TeamID          *int64       `json:"team_id"`
	Chunks          []chunkEntry `json:"chunks"`
}

type chunkEntry struct {
	ChunkID string `json:"chunk_id"`
	Text    string `json:"text"`
}

func EmbedChunksToLocalIndex(document DocumentPayload, chunksRoot string, vectorRoot string) (Result, error) {
	chunkRelativePath, err := buildChunkRelativePath(
		document.Scope,
		document.KnowledgeBaseID,
		document.DocumentID,
		document.TeamID,
	)
	if err != nil {
		return Result{}, err
	}

	chunkSource := filepath.Join(chunksRoot, filepath.FromSlash(chunkRelativePath))
	body, err := os.ReadFile(chunkSource)
	if err != nil {
		if os.IsNotExist(err) {
			return Result{}, fmt.Errorf("document chunk result does not exist")
		}
		return Result{}, fmt.Errorf("failed to read document chunk result: %w", err)
	}

	var payload chunkPayload
	if err := json.Unmarshal(body, &payload); err != nil {
		return Result{}, fmt.Errorf("document chunk result is not valid JSON")
	}
	if len(payload.Chunks) == 0 {
		return Result{}, fmt.Errorf("document chunk result does not contain chunks")
	}

	entries := make([]map[string]any, 0, len(payload.Chunks))
	for _, item := range payload.Chunks {
		if item.ChunkID == "" || item.Text == "" {
			return Result{}, fmt.Errorf("document chunk entry is missing required fields")
		}

		vector, err := buildTextEmbedding(item.Text, EmbeddingDimension)
		if err != nil {
			return Result{}, err
		}

		entries = append(entries, map[string]any{
			"chunk_id":          item.ChunkID,
			"document_id":       document.DocumentID,
			"knowledge_base_id": document.KnowledgeBaseID,
			"scope":             document.Scope,
			"team_id":           document.TeamID,
			"text":              item.Text,
			"vector":            vector,
		})
	}

	indexRelativePath, err := buildIndexRelativePath(
		document.Scope,
		document.KnowledgeBaseID,
		document.TeamID,
	)
	if err != nil {
		return Result{}, err
	}

	destination := filepath.Join(vectorRoot, filepath.FromSlash(indexRelativePath))
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return Result{}, fmt.Errorf("failed to prepare vector index directory: %w", err)
	}

	indexPayload, err := loadIndexPayload(destination)
	if err != nil {
		return Result{}, err
	}

	indexPayload["embedding_scheme"] = EmbeddingScheme
	indexPayload["embedding_dimension"] = EmbeddingDimension
	indexPayload["scope"] = document.Scope
	indexPayload["team_id"] = document.TeamID
	indexPayload["knowledge_base_id"] = document.KnowledgeBaseID

	filteredDocuments := make([]any, 0)
	if existingDocuments, ok := indexPayload["documents"].([]any); ok {
		for _, item := range existingDocuments {
			entry, ok := item.(map[string]any)
			if !ok {
				continue
			}
			if matchesDocumentID(entry["document_id"], document.DocumentID) {
				continue
			}
			filteredDocuments = append(filteredDocuments, entry)
		}
	}

	filteredDocuments = append(filteredDocuments, map[string]any{
		"document_id":          document.DocumentID,
		"chunk_source_path":    chunkRelativePath,
		"embedded_chunk_count": len(entries),
		"chunks":               entries,
	})
	indexPayload["documents"] = filteredDocuments

	encoded, err := json.MarshalIndent(indexPayload, "", "  ")
	if err != nil {
		return Result{}, fmt.Errorf("failed to encode vector index payload: %w", err)
	}
	if err := os.WriteFile(destination, encoded, 0o644); err != nil {
		return Result{}, fmt.Errorf("failed to write vector index: %w", err)
	}

	return Result{
		IndexPath:          indexRelativePath,
		EmbeddedChunkCount: len(entries),
		EmbeddingDimension: EmbeddingDimension,
		SourceChunkPath:    chunkRelativePath,
	}, nil
}

func buildTextEmbedding(text string, dimension int) ([]float64, error) {
	tokens := tokenizeText(text)
	if len(tokens) == 0 {
		return nil, fmt.Errorf("text contains no tokens for embedding")
	}

	vector := make([]float64, dimension)
	for _, token := range tokens {
		digest := sha256.Sum256([]byte(token))
		index := int(binary.BigEndian.Uint32(digest[:4]) % uint32(dimension))
		sign := 1.0
		if digest[4]%2 != 0 {
			sign = -1.0
		}
		vector[index] += sign
	}

	var magnitude float64
	for _, value := range vector {
		magnitude += value * value
	}
	magnitude = math.Sqrt(magnitude)
	if magnitude == 0 {
		return nil, fmt.Errorf("text embedding could not be normalized")
	}

	for index, value := range vector {
		vector[index] = value / magnitude
	}
	return vector, nil
}

func tokenizeText(text string) []string {
	return tokenPattern.FindAllString(strings.ToLower(strings.TrimSpace(text)), -1)
}

func loadIndexPayload(path string) (map[string]any, error) {
	body, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return map[string]any{"documents": []any{}}, nil
		}
		return nil, fmt.Errorf("failed to read vector index: %w", err)
	}

	var payload map[string]any
	if err := json.Unmarshal(body, &payload); err != nil {
		return nil, fmt.Errorf("vector index is not valid JSON")
	}
	if payload == nil {
		return nil, fmt.Errorf("vector index is not valid")
	}
	if _, ok := payload["documents"]; !ok {
		payload["documents"] = []any{}
	}
	return payload, nil
}

func matchesDocumentID(value any, documentID int64) bool {
	switch typed := value.(type) {
	case float64:
		return int64(typed) == documentID
	case int64:
		return typed == documentID
	case int:
		return int64(typed) == documentID
	default:
		return false
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
			return "", fmt.Errorf("team_id is required for team document embedding")
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

func buildIndexRelativePath(scope string, knowledgeBaseID int64, teamID *int64) (string, error) {
	switch scope {
	case "personal":
		return path.Join(
			"personal",
			fmt.Sprintf("knowledge_base_%d", knowledgeBaseID),
			"index.json",
		), nil
	case "team":
		if teamID == nil {
			return "", fmt.Errorf("team_id is required for team vector index")
		}
		return path.Join(
			"team",
			fmt.Sprintf("team_%d", *teamID),
			fmt.Sprintf("knowledge_base_%d", knowledgeBaseID),
			"index.json",
		), nil
	default:
		return "", fmt.Errorf("unsupported knowledge base scope: %s", scope)
	}
}
