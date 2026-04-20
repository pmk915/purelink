package embedder

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestEmbedChunksToLocalIndex(t *testing.T) {
	tempDir := t.TempDir()
	chunksRoot := filepath.Join(tempDir, "chunks")
	vectorRoot := filepath.Join(tempDir, "vector_store")

	chunkPath := filepath.Join(chunksRoot, "personal", "knowledge_base_7", "document_12.json")
	if err := os.MkdirAll(filepath.Dir(chunkPath), 0o755); err != nil {
		t.Fatalf("failed to create chunk directory: %v", err)
	}

	chunkPayload := map[string]any{
		"document_id":       12,
		"knowledge_base_id": 7,
		"scope":             "personal",
		"team_id":           nil,
		"chunks": []map[string]any{
			{
				"index":      0,
				"chunk_id":   "12:0",
				"char_count": 11,
				"text":       "Alpha beta",
			},
			{
				"index":      1,
				"chunk_id":   "12:1",
				"char_count": 10,
				"text":       "Gamma 文档",
			},
		},
	}
	body, err := json.Marshal(chunkPayload)
	if err != nil {
		t.Fatalf("failed to marshal chunk payload: %v", err)
	}
	if err := os.WriteFile(chunkPath, body, 0o644); err != nil {
		t.Fatalf("failed to write chunk payload: %v", err)
	}

	result, err := EmbedChunksToLocalIndex(
		DocumentPayload{
			DocumentID:      12,
			KnowledgeBaseID: 7,
			Scope:           "personal",
		},
		chunksRoot,
		vectorRoot,
	)
	if err != nil {
		t.Fatalf("EmbedChunksToLocalIndex returned error: %v", err)
	}

	if result.IndexPath != "personal/knowledge_base_7/index.json" {
		t.Fatalf("unexpected index path: %s", result.IndexPath)
	}
	if result.SourceChunkPath != "personal/knowledge_base_7/document_12.json" {
		t.Fatalf("unexpected source chunk path: %s", result.SourceChunkPath)
	}
	if result.EmbeddedChunkCount != 2 {
		t.Fatalf("expected 2 embedded chunks, got %d", result.EmbeddedChunkCount)
	}

	indexBody, err := os.ReadFile(filepath.Join(vectorRoot, filepath.FromSlash(result.IndexPath)))
	if err != nil {
		t.Fatalf("failed to read index payload: %v", err)
	}

	var indexPayload map[string]any
	if err := json.Unmarshal(indexBody, &indexPayload); err != nil {
		t.Fatalf("failed to unmarshal index payload: %v", err)
	}
	if indexPayload["embedding_scheme"] != EmbeddingScheme {
		t.Fatalf("unexpected embedding scheme: %v", indexPayload["embedding_scheme"])
	}
	if int(indexPayload["embedding_dimension"].(float64)) != EmbeddingDimension {
		t.Fatalf("unexpected embedding dimension: %v", indexPayload["embedding_dimension"])
	}

	documents, ok := indexPayload["documents"].([]any)
	if !ok || len(documents) != 1 {
		t.Fatalf("expected one document entry, got %#v", indexPayload["documents"])
	}
	documentEntry, ok := documents[0].(map[string]any)
	if !ok {
		t.Fatalf("unexpected document entry payload: %#v", documents[0])
	}
	if documentEntry["chunk_source_path"] != "personal/knowledge_base_7/document_12.json" {
		t.Fatalf("unexpected chunk_source_path: %v", documentEntry["chunk_source_path"])
	}

	chunks, ok := documentEntry["chunks"].([]any)
	if !ok || len(chunks) != 2 {
		t.Fatalf("expected 2 embedded chunks, got %#v", documentEntry["chunks"])
	}
	firstChunk, ok := chunks[0].(map[string]any)
	if !ok {
		t.Fatalf("unexpected chunk payload: %#v", chunks[0])
	}
	vector, ok := firstChunk["vector"].([]any)
	if !ok || len(vector) != EmbeddingDimension {
		t.Fatalf("expected %d-dimensional vector, got %#v", EmbeddingDimension, firstChunk["vector"])
	}
}

func TestEmbedChunksToLocalIndexReplacesExistingDocumentEntry(t *testing.T) {
	tempDir := t.TempDir()
	chunksRoot := filepath.Join(tempDir, "chunks")
	vectorRoot := filepath.Join(tempDir, "vector_store")

	chunkPath := filepath.Join(chunksRoot, "team", "team_9", "knowledge_base_4", "document_8.json")
	if err := os.MkdirAll(filepath.Dir(chunkPath), 0o755); err != nil {
		t.Fatalf("failed to create chunk directory: %v", err)
	}
	if err := os.MkdirAll(filepath.Join(vectorRoot, "team", "team_9", "knowledge_base_4"), 0o755); err != nil {
		t.Fatalf("failed to create vector directory: %v", err)
	}

	chunkPayload := map[string]any{
		"document_id":       8,
		"knowledge_base_id": 4,
		"scope":             "team",
		"team_id":           9,
		"chunks": []map[string]any{
			{
				"index":      0,
				"chunk_id":   "8:0",
				"char_count": 12,
				"text":       "updated text",
			},
		},
	}
	body, err := json.Marshal(chunkPayload)
	if err != nil {
		t.Fatalf("failed to marshal chunk payload: %v", err)
	}
	if err := os.WriteFile(chunkPath, body, 0o644); err != nil {
		t.Fatalf("failed to write chunk payload: %v", err)
	}

	indexPath := filepath.Join(vectorRoot, "team", "team_9", "knowledge_base_4", "index.json")
	indexPayload := map[string]any{
		"documents": []map[string]any{
			{
				"document_id":          8,
				"chunk_source_path":    "stale.json",
				"embedded_chunk_count": 1,
				"chunks": []map[string]any{
					{"chunk_id": "old", "text": "old", "vector": []float64{1}},
				},
			},
			{
				"document_id":          10,
				"chunk_source_path":    "keep.json",
				"embedded_chunk_count": 1,
				"chunks": []map[string]any{
					{"chunk_id": "keep", "text": "keep", "vector": []float64{1}},
				},
			},
		},
	}
	indexBody, err := json.Marshal(indexPayload)
	if err != nil {
		t.Fatalf("failed to marshal existing index: %v", err)
	}
	if err := os.WriteFile(indexPath, indexBody, 0o644); err != nil {
		t.Fatalf("failed to write existing index: %v", err)
	}

	teamID := int64(9)
	if _, err := EmbedChunksToLocalIndex(
		DocumentPayload{
			DocumentID:      8,
			KnowledgeBaseID: 4,
			Scope:           "team",
			TeamID:          &teamID,
		},
		chunksRoot,
		vectorRoot,
	); err != nil {
		t.Fatalf("EmbedChunksToLocalIndex returned error: %v", err)
	}

	updatedBody, err := os.ReadFile(indexPath)
	if err != nil {
		t.Fatalf("failed to read updated index: %v", err)
	}

	var updatedPayload map[string]any
	if err := json.Unmarshal(updatedBody, &updatedPayload); err != nil {
		t.Fatalf("failed to unmarshal updated index: %v", err)
	}

	documents, ok := updatedPayload["documents"].([]any)
	if !ok || len(documents) != 2 {
		t.Fatalf("expected 2 document entries, got %#v", updatedPayload["documents"])
	}

	replaced := false
	preserved := false
	for _, item := range documents {
		entry, ok := item.(map[string]any)
		if !ok {
			continue
		}

		switch int64(entry["document_id"].(float64)) {
		case 8:
			replaced = entry["chunk_source_path"] == "team/team_9/knowledge_base_4/document_8.json"
		case 10:
			preserved = entry["chunk_source_path"] == "keep.json"
		}
	}

	if !replaced {
		t.Fatalf("expected document 8 entry to be replaced")
	}
	if !preserved {
		t.Fatalf("expected unrelated document entry to remain")
	}
}
