package tasks

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"time"

	"purelink/worker-go/internal/chunker"
	"purelink/worker-go/internal/embedder"
	"purelink/worker-go/internal/parser"
)

const (
	taskTypeParse = "parse"
	taskTypeChunk = "chunk"
	taskTypeEmbed = "embed"
	taskTypeIndex = "index"
)

type Worker struct {
	db           *sql.DB
	uploadRoot   string
	parsedRoot   string
	chunksRoot   string
	vectorRoot   string
	pollInterval time.Duration
	logger       *log.Logger
}

type claimedTask struct {
	TaskID           int64
	DocumentID       int64
	TaskType         string
	KnowledgeBaseID  int64
	OriginalFilename string
	StoragePath      string
	ReviewStatus     string
	ProcessingStatus string
	Scope            string
	TeamID           *int64
}

func NewWorker(
	db *sql.DB,
	uploadRoot string,
	parsedRoot string,
	chunksRoot string,
	vectorRoot string,
	pollInterval time.Duration,
	logger *log.Logger,
) *Worker {
	return &Worker{
		db:           db,
		uploadRoot:   uploadRoot,
		parsedRoot:   parsedRoot,
		chunksRoot:   chunksRoot,
		vectorRoot:   vectorRoot,
		pollInterval: pollInterval,
		logger:       logger,
	}
}

func (w *Worker) Run(ctx context.Context) error {
	if err := w.runAvailable(ctx); err != nil {
		return err
	}

	ticker := time.NewTicker(w.pollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-ticker.C:
			if err := w.runAvailable(ctx); err != nil {
				return err
			}
		}
	}
}

func (w *Worker) runAvailable(ctx context.Context) error {
	for {
		task, err := claimNextSupportedTask(ctx, w.db)
		if err != nil {
			return err
		}
		if task == nil {
			return nil
		}

		w.logger.Printf("claimed %s task id=%d document_id=%d", task.TaskType, task.TaskID, task.DocumentID)
		if err := w.processTask(ctx, task); err != nil {
			w.logger.Printf("%s task id=%d failed: %v", task.TaskType, task.TaskID, err)
		}
	}
}

func (w *Worker) processTask(ctx context.Context, task *claimedTask) error {
	switch task.TaskType {
	case taskTypeParse:
		return w.processParseTask(ctx, task)
	case taskTypeChunk:
		return w.processChunkTask(ctx, task)
	case taskTypeEmbed, taskTypeIndex:
		return w.processEmbeddingTask(ctx, task)
	default:
		return failTask(ctx, w.db, task.TaskID, task.DocumentID, task.TaskType, fmt.Errorf("unsupported task_type: %s", task.TaskType))
	}
}

func (w *Worker) processParseTask(ctx context.Context, task *claimedTask) error {
	if err := validateParseEligibility(task); err != nil {
		return failTask(ctx, w.db, task.TaskID, task.DocumentID, task.TaskType, err)
	}

	result, err := parser.ParseDocumentToLocalResult(
		parser.DocumentPayload{
			DocumentID:       task.DocumentID,
			KnowledgeBaseID:  task.KnowledgeBaseID,
			OriginalFilename: task.OriginalFilename,
			StoragePath:      task.StoragePath,
			Scope:            task.Scope,
			TeamID:           task.TeamID,
		},
		w.uploadRoot,
		w.parsedRoot,
	)
	if err != nil {
		return failTask(ctx, w.db, task.TaskID, task.DocumentID, task.TaskType, err)
	}

	if err := markTaskSucceeded(ctx, w.db, task.TaskID, task.DocumentID, task.TaskType); err != nil {
		return fmt.Errorf("failed to mark task as succeeded: %w", err)
	}

	w.logger.Printf(
		"parse task id=%d succeeded document_id=%d parsed_path=%s parser=%s",
		task.TaskID,
		task.DocumentID,
		result.ParsedPath,
		result.Parser,
	)
	return nil
}

func (w *Worker) processChunkTask(ctx context.Context, task *claimedTask) error {
	if err := validateChunkEligibility(task); err != nil {
		return failTask(ctx, w.db, task.TaskID, task.DocumentID, task.TaskType, err)
	}

	result, err := chunker.ChunkDocumentFromParsedResult(
		chunker.DocumentPayload{
			DocumentID:      task.DocumentID,
			KnowledgeBaseID: task.KnowledgeBaseID,
			Scope:           task.Scope,
			TeamID:          task.TeamID,
		},
		w.parsedRoot,
		w.chunksRoot,
	)
	if err != nil {
		return failTask(ctx, w.db, task.TaskID, task.DocumentID, task.TaskType, err)
	}

	if err := markTaskSucceeded(ctx, w.db, task.TaskID, task.DocumentID, task.TaskType); err != nil {
		return fmt.Errorf("failed to mark task as succeeded: %w", err)
	}

	w.logger.Printf(
		"chunk task id=%d succeeded document_id=%d chunked_path=%s chunk_count=%d",
		task.TaskID,
		task.DocumentID,
		result.ChunkedPath,
		result.ChunkCount,
	)
	return nil
}

func (w *Worker) processEmbeddingTask(ctx context.Context, task *claimedTask) error {
	if err := validateEmbeddingEligibility(task); err != nil {
		return failTask(ctx, w.db, task.TaskID, task.DocumentID, task.TaskType, err)
	}

	result, err := embedder.EmbedChunksToLocalIndex(
		embedder.DocumentPayload{
			DocumentID:      task.DocumentID,
			KnowledgeBaseID: task.KnowledgeBaseID,
			Scope:           task.Scope,
			TeamID:          task.TeamID,
		},
		w.chunksRoot,
		w.vectorRoot,
	)
	if err != nil {
		return failTask(ctx, w.db, task.TaskID, task.DocumentID, task.TaskType, err)
	}

	if err := markTaskSucceeded(ctx, w.db, task.TaskID, task.DocumentID, task.TaskType); err != nil {
		return fmt.Errorf("failed to mark task as succeeded: %w", err)
	}

	w.logger.Printf(
		"%s task id=%d succeeded document_id=%d index_path=%s embedded_chunk_count=%d",
		task.TaskType,
		task.TaskID,
		task.DocumentID,
		result.IndexPath,
		result.EmbeddedChunkCount,
	)
	return nil
}

func validateParseEligibility(task *claimedTask) error {
	switch task.Scope {
	case "personal":
		if task.ReviewStatus != "not_required" {
			return fmt.Errorf("personal document is not eligible for parsing")
		}
	case "team":
		if task.TeamID == nil {
			return fmt.Errorf("team document is missing team_id")
		}
		if task.ReviewStatus != "approved" {
			return fmt.Errorf("team document is not eligible for parsing")
		}
	default:
		return fmt.Errorf("unsupported knowledge base scope: %s", task.Scope)
	}

	return nil
}

func validateChunkEligibility(task *claimedTask) error {
	if err := validateParseEligibility(task); err != nil {
		return err
	}
	if task.ProcessingStatus != "parsed" {
		return fmt.Errorf("document must be parsed before chunking")
	}
	return nil
}

func validateEmbeddingEligibility(task *claimedTask) error {
	if err := validateParseEligibility(task); err != nil {
		return err
	}
	if task.ProcessingStatus != "parsed" && task.ProcessingStatus != "indexed" {
		return fmt.Errorf("document must be chunked and parsed before embedding or indexing")
	}
	return nil
}

func claimNextSupportedTask(ctx context.Context, db *sql.DB) (*claimedTask, error) {
	const query = `
WITH next_task AS (
    SELECT dt.id
    FROM document_tasks AS dt
    WHERE dt.task_type IN ('parse', 'chunk', 'embed', 'index')
      AND dt.status = 'pending'
    ORDER BY dt.id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE document_tasks AS dt
SET status = 'processing',
    started_at = NOW(),
    updated_at = NOW()
FROM documents AS d
JOIN knowledge_bases AS kb
  ON kb.id = d.knowledge_base_id
WHERE dt.id = (SELECT id FROM next_task)
  AND d.id = dt.document_id
RETURNING
  dt.id,
  dt.document_id,
  dt.task_type,
  d.knowledge_base_id,
  d.original_filename,
  d.storage_path,
  d.review_status,
  d.processing_status,
  kb.scope,
  kb.team_id
`

	var (
		task   claimedTask
		teamID sql.NullInt64
	)

	err := db.QueryRowContext(ctx, query).Scan(
		&task.TaskID,
		&task.DocumentID,
		&task.TaskType,
		&task.KnowledgeBaseID,
		&task.OriginalFilename,
		&task.StoragePath,
		&task.ReviewStatus,
		&task.ProcessingStatus,
		&task.Scope,
		&teamID,
	)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, fmt.Errorf("failed to claim task: %w", err)
	}

	if teamID.Valid {
		task.TeamID = &teamID.Int64
	}
	return &task, nil
}

func markTaskSucceeded(ctx context.Context, db *sql.DB, taskID int64, documentID int64, taskType string) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("failed to begin success transaction: %w", err)
	}
	defer tx.Rollback()

	if _, err := tx.ExecContext(
		ctx,
		`
UPDATE document_tasks
SET status = 'succeeded',
    error_message = NULL,
    finished_at = NOW(),
    updated_at = NOW()
WHERE id = $1
`,
		taskID,
	); err != nil {
		return fmt.Errorf("failed to update task success state: %w", err)
	}

	if taskType == taskTypeParse {
		if _, err := tx.ExecContext(
			ctx,
			`
UPDATE documents
SET processing_status = 'parsed',
    updated_at = NOW()
WHERE id = $1
`,
			documentID,
		); err != nil {
			return fmt.Errorf("failed to update document parsed state: %w", err)
		}
	}

	if taskType == taskTypeEmbed || taskType == taskTypeIndex {
		if _, err := tx.ExecContext(
			ctx,
			`
UPDATE documents
SET processing_status = 'indexed',
    updated_at = NOW()
WHERE id = $1
`,
			documentID,
		); err != nil {
			return fmt.Errorf("failed to update document indexed state: %w", err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit success transaction: %w", err)
	}
	return nil
}

func failTask(ctx context.Context, db *sql.DB, taskID int64, documentID int64, taskType string, cause error) error {
	tx, err := db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("failed to begin failure transaction: %w", err)
	}
	defer tx.Rollback()

	if _, err := tx.ExecContext(
		ctx,
		`
UPDATE document_tasks
SET status = 'failed',
    error_message = $2,
    retry_count = retry_count + 1,
    finished_at = NOW(),
    updated_at = NOW()
WHERE id = $1
`,
		taskID,
		cause.Error(),
	); err != nil {
		return fmt.Errorf("failed to update task failure state: %w", err)
	}

	if taskType == taskTypeParse || taskType == taskTypeEmbed || taskType == taskTypeIndex {
		if _, err := tx.ExecContext(
			ctx,
			`
UPDATE documents
SET processing_status = 'failed',
    updated_at = NOW()
WHERE id = $1
`,
			documentID,
		); err != nil {
			return fmt.Errorf("failed to update document failure state: %w", err)
		}
	}

	if err := tx.Commit(); err != nil {
		return fmt.Errorf("failed to commit failure transaction: %w", err)
	}
	return cause
}
