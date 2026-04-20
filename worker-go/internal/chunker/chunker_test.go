package chunker

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestSplitTextIntoChunks(t *testing.T) {
	text := "First block.\n\nSecond block.\n\nThird block."
	chunks, err := SplitTextIntoChunks(text, 20)
	if err != nil {
		t.Fatalf("SplitTextIntoChunks returned error: %v", err)
	}

	if len(chunks) != 3 {
		t.Fatalf("expected 3 chunks, got %d", len(chunks))
	}
	if chunks[0] != "First block." {
		t.Fatalf("unexpected first chunk: %q", chunks[0])
	}
}

func TestChunkDocumentFromParsedResult(t *testing.T) {
	tempDir := t.TempDir()
	parsedRoot := filepath.Join(tempDir, "parsed")
	chunksRoot := filepath.Join(tempDir, "chunks")

	parsedPath := filepath.Join(parsedRoot, "personal", "knowledge_base_3", "document_12.json")
	if err := os.MkdirAll(filepath.Dir(parsedPath), 0o755); err != nil {
		t.Fatalf("failed to create parsed directory: %v", err)
	}

	parsedPayload := map[string]any{
		"document_id":          12,
		"knowledge_base_id":    3,
		"scope":                "personal",
		"team_id":              nil,
		"original_filename":    "notes.txt",
		"source_storage_path":  "personal/knowledge_base_3/source.txt",
		"parser":               "plain_text",
		"extracted_char_count": 24,
		"content":              "First block.\n\nSecond block.",
	}
	body, err := json.Marshal(parsedPayload)
	if err != nil {
		t.Fatalf("failed to marshal parsed payload: %v", err)
	}
	if err := os.WriteFile(parsedPath, body, 0o644); err != nil {
		t.Fatalf("failed to write parsed payload: %v", err)
	}

	result, err := ChunkDocumentFromParsedResult(
		DocumentPayload{
			DocumentID:      12,
			KnowledgeBaseID: 3,
			Scope:           "personal",
		},
		parsedRoot,
		chunksRoot,
	)
	if err != nil {
		t.Fatalf("ChunkDocumentFromParsedResult returned error: %v", err)
	}

	if result.ChunkedPath != "personal/knowledge_base_3/document_12.json" {
		t.Fatalf("unexpected chunked path: %s", result.ChunkedPath)
	}
	if result.SourceParsedPath != "personal/knowledge_base_3/document_12.json" {
		t.Fatalf("unexpected source parsed path: %s", result.SourceParsedPath)
	}
	if result.ChunkCount != 1 {
		t.Fatalf("expected 1 chunk, got %d", result.ChunkCount)
	}

	chunkBody, err := os.ReadFile(filepath.Join(chunksRoot, filepath.FromSlash(result.ChunkedPath)))
	if err != nil {
		t.Fatalf("failed to read chunk result: %v", err)
	}
	var chunkPayload map[string]any
	if err := json.Unmarshal(chunkBody, &chunkPayload); err != nil {
		t.Fatalf("failed to unmarshal chunk result: %v", err)
	}
	if chunkPayload["source_parsed_path"] != "personal/knowledge_base_3/document_12.json" {
		t.Fatalf("unexpected source_parsed_path: %v", chunkPayload["source_parsed_path"])
	}
	chunks, ok := chunkPayload["chunks"].([]any)
	if !ok || len(chunks) != 1 {
		t.Fatalf("expected one chunk entry, got %#v", chunkPayload["chunks"])
	}
}
