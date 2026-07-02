import { z } from "zod";

export const rejectDocumentSchema = z.object({
  review_comment: z.string().min(1, "Rejection reason is required.")
});

export type RejectDocumentValues = z.infer<typeof rejectDocumentSchema>;

export const documentStatusCheckSchema = z.object({
  name: z.string(),
  label: z.string(),
  status: z.enum(["ready", "missing", "warning", "failed", "optional", "pending"]),
  count: z.number().nullable(),
  message: z.string()
});

export const processingJobStatusSchema = z.enum([
  "queued",
  "processing",
  "retrying",
  "succeeded",
  "failed",
  "cancelled"
]);

export const processingJobSummarySchema = z.object({
  id: z.number(),
  job_id: z.number(),
  document_id: z.number(),
  document_status: z.enum(["uploaded", "processing", "parsed", "indexed", "ready", "failed"]),
  filename: z.string(),
  status: processingJobStatusSchema,
  job_status: processingJobStatusSchema,
  current_step: z.string().nullable(),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
  attempt_count: z.number(),
  max_attempts: z.number(),
  retry_count: z.number(),
  max_retries: z.number(),
  can_retry: z.boolean(),
  job_type: z.enum(["document_process", "document_index"]),
  trigger_type: z.enum(["process", "retry", "reprocess", "index"]),
  created_at: z.string(),
  updated_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable()
});

export const processingJobListSchema = z.object({
  items: z.array(processingJobSummarySchema),
  total: z.number(),
  failed_count: z.number(),
  running_count: z.number(),
  completed_count: z.number()
});

export const documentStatusSchema = z.object({
  document_id: z.number(),
  kb_id: z.number(),
  filename: z.string(),
  processing_status: z.enum(["uploaded", "processing", "parsed", "indexed", "ready", "failed"]),
  rag_ready: z.boolean(),
  block_count: z.number(),
  chunk_count: z.number(),
  citation_unit_count: z.number(),
  vector_index_status: z.enum(["ready", "missing", "warning", "failed", "optional", "pending"]),
  vector_index_count: z.number(),
  vector_index_compatible: z.boolean().nullable(),
  graph_index_status: z.enum(["ready", "missing", "warning", "failed", "optional", "pending"]),
  entity_count: z.number(),
  relation_count: z.number(),
  latest_processing_job_step: z.string().nullable(),
  latest_processing_job_status: processingJobStatusSchema.nullable(),
  latest_processing_job_id: z.number().nullable(),
  latest_processing_job_attempt_count: z.number().nullable(),
  latest_processing_job_max_attempts: z.number().nullable(),
  latest_processing_job_can_retry: z.boolean(),
  latest_processing_job_error_code: z.string().nullable(),
  latest_processing_job_error_message: z.string().nullable(),
  error_code: z.string().nullable(),
  error_message: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  last_indexed_at: z.string().nullable(),
  warnings: z.array(z.string()),
  checks: z.array(documentStatusCheckSchema)
});
