package parser

import (
	"encoding/json"
	"fmt"
	"os"
	"path"
	"path/filepath"
	"strings"
	"unicode/utf8"
)

var supportedParseSuffixes = map[string]string{
	".txt": "plain_text",
	".md":  "markdown",
}

type DocumentPayload struct {
	DocumentID       int64
	KnowledgeBaseID  int64
	OriginalFilename string
	StoragePath      string
	Scope            string
	TeamID           *int64
}

type Result struct {
	ParsedPath         string
	Parser             string
	ExtractedCharCount int
}

type parsedDocumentPayload struct {
	DocumentID         int64  `json:"document_id"`
	KnowledgeBaseID    int64  `json:"knowledge_base_id"`
	Scope              string `json:"scope"`
	TeamID             *int64 `json:"team_id"`
	OriginalFilename   string `json:"original_filename"`
	SourceStoragePath  string `json:"source_storage_path"`
	Parser             string `json:"parser"`
	ExtractedCharCount int    `json:"extracted_char_count"`
	Content            string `json:"content"`
}

func ParseDocumentToLocalResult(document DocumentPayload, uploadRoot string, parsedRoot string) (Result, error) {
	sourcePath, err := resolveSourcePath(uploadRoot, document.StoragePath)
	if err != nil {
		return Result{}, err
	}

	content, parserName, err := extractText(sourcePath, document.OriginalFilename)
	if err != nil {
		return Result{}, err
	}

	relativePath, err := buildParsedRelativePath(
		document.Scope,
		document.KnowledgeBaseID,
		document.DocumentID,
		document.TeamID,
	)
	if err != nil {
		return Result{}, err
	}

	destination := filepath.Join(parsedRoot, filepath.FromSlash(relativePath))
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return Result{}, fmt.Errorf("failed to prepare parsed output directory: %w", err)
	}

	payload := parsedDocumentPayload{
		DocumentID:         document.DocumentID,
		KnowledgeBaseID:    document.KnowledgeBaseID,
		Scope:              document.Scope,
		TeamID:             document.TeamID,
		OriginalFilename:   document.OriginalFilename,
		SourceStoragePath:  document.StoragePath,
		Parser:             parserName,
		ExtractedCharCount: utf8.RuneCountInString(content),
		Content:            content,
	}

	body, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return Result{}, fmt.Errorf("failed to encode parsed payload: %w", err)
	}
	body = append(body, '\n')

	if err := os.WriteFile(destination, body, 0o644); err != nil {
		return Result{}, fmt.Errorf("failed to write parsed result: %w", err)
	}

	return Result{
		ParsedPath:         relativePath,
		Parser:             parserName,
		ExtractedCharCount: utf8.RuneCountInString(content),
	}, nil
}

func resolveSourcePath(uploadRoot string, storagePath string) (string, error) {
	if filepath.IsAbs(storagePath) {
		return "", fmt.Errorf("document storage path must be relative")
	}

	cleanStoragePath := filepath.Clean(storagePath)
	if cleanStoragePath == ".." || strings.HasPrefix(cleanStoragePath, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("document storage path is invalid")
	}

	sourcePath := filepath.Join(uploadRoot, cleanStoragePath)
	if _, err := os.Stat(sourcePath); err != nil {
		if os.IsNotExist(err) {
			return "", fmt.Errorf("document source file does not exist")
		}
		return "", fmt.Errorf("failed to stat document source file: %w", err)
	}
	return sourcePath, nil
}

func extractText(sourcePath string, originalFilename string) (string, string, error) {
	suffix := strings.ToLower(filepath.Ext(originalFilename))
	parserName, ok := supportedParseSuffixes[suffix]
	if !ok {
		return "", "", fmt.Errorf("only .txt and .md documents are supported for parsing")
	}

	body, err := os.ReadFile(sourcePath)
	if err != nil {
		return "", "", fmt.Errorf("failed to read document source file: %w", err)
	}
	if !utf8.Valid(body) {
		return "", "", fmt.Errorf("document could not be decoded as UTF-8 text")
	}

	return string(body), parserName, nil
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
			return "", fmt.Errorf("team_id is required for team document parsing")
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
