import type { AskResponseContract, CitationContract } from "@/schemas/qa";

export type KnowledgeBaseScope = "personal" | "team";
export type RetrievalMode = "auto" | "chunk_only" | "overview" | "graph_vector_mix" | "hybrid_text";
export type TeamMemberRole = "admin" | "member";
export type TeamMemberStatus = "active" | "invited" | "removed";
export type TeamInviteStatus = "active" | "used" | "expired" | "revoked";
export type DocumentReviewStatus =
  | "not_required"
  | "pending_review"
  | "approved"
  | "rejected";
export type DocumentProcessingStatus =
  | "uploaded"
  | "processing"
  | "parsed"
  | "indexed"
  | "ready"
  | "failed";
export type DocumentTaskType = "parse" | "chunk" | "embed" | "index";
export type DocumentTaskStatus = "pending" | "processing" | "succeeded" | "failed";
export type ProcessingJobType = "document_process" | "document_index";
export type ProcessingJobStatus =
  | "queued"
  | "processing"
  | "retrying"
  | "succeeded"
  | "failed"
  | "cancelled";
export type ProcessingJobTrigger = "process" | "retry" | "reprocess" | "index";
export type MessageRole = "system" | "user" | "assistant";

export interface ApiErrorPayload {
  error?: {
    code: string;
    message: string;
    details?: Record<string, unknown> | null;
    request_id?: string | null;
  };
  detail?:
    | string
     | {
        code?: string;
        error_code?: string;
        message?: string;
        detail?: string;
        document_id?: string;
        [key: string]: unknown;
      };
}

export interface UploadConstraints {
  max_upload_size_mb: number;
  max_upload_size_bytes: number;
  allowed_extensions: string[];
  allowed_mime_types: string[];
}

export interface User {
  id: number;
  email: string;
  username: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface KnowledgeBase {
  id: number;
  name: string;
  description: string | null;
  scope: KnowledgeBaseScope;
  owner_id: number | null;
  team_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeBaseRagHealth {
  document_count: number;
  document_status_counts: Record<string, number>;
  index_status_counts: Record<string, Record<string, number>>;
}

export interface Team {
  id: number;
  name: string;
  description: string | null;
  created_by: number;
  created_at: string;
  updated_at: string;
  my_role: TeamMemberRole;
  my_status: TeamMemberStatus;
}

export interface TeamInvite {
  id: number;
  team_id: number;
  code: string;
  invited_by: number;
  expires_at: string;
  used_by: number | null;
  used_at: string | null;
  status: TeamInviteStatus;
  created_at: string;
  updated_at: string;
}

export interface TeamMemberUser {
  id: number;
  email: string;
  username: string;
}

export interface TeamMember {
  id: number;
  team_id: number;
  user_id: number;
  role: TeamMemberRole;
  status: TeamMemberStatus;
  joined_at: string | null;
  created_at: string;
  updated_at: string;
  user: TeamMemberUser;
}

export interface Document {
  id: number;
  knowledge_base_id: number;
  owner_id: number;
  submitted_by: number;
  filename: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  sha256: string | null;
  storage_path: string;
  review_status: DocumentReviewStatus;
  processing_status: DocumentProcessingStatus;
  reviewed_by: number | null;
  reviewed_at: string | null;
  review_comment: string | null;
  error_message: string | null;
  processed_at: string | null;
  latest_processing_job_id: number | null;
  latest_processing_job_status: ProcessingJobStatus | null;
  latest_processing_job_type: ProcessingJobType | null;
  latest_processing_job_step: string | null;
  latest_processing_job_error_code: string | null;
  latest_processing_job_trigger: ProcessingJobTrigger | null;
  latest_processing_job_attempt_number: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProcessingJobSubmission {
  document_id: number;
  document_status: DocumentProcessingStatus;
  job_id: number;
  job_type: ProcessingJobType;
  job_status: ProcessingJobStatus;
  trigger_type: ProcessingJobTrigger;
  attempt_number: number;
}

export interface ProcessingJobSummary {
  id: number;
  job_id: number;
  document_id: number;
  document_status: DocumentProcessingStatus;
  filename: string;
  status: ProcessingJobStatus;
  job_status: ProcessingJobStatus;
  current_step: string | null;
  error_code: string | null;
  error_message: string | null;
  attempt_count: number;
  max_attempts: number;
  retry_count: number;
  max_retries: number;
  can_retry: boolean;
  job_type: ProcessingJobType;
  trigger_type: ProcessingJobTrigger;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ProcessingJobList {
  items: ProcessingJobSummary[];
  total: number;
  failed_count: number;
  running_count: number;
  completed_count: number;
}

export interface DocumentTask {
  id: number;
  document_id: number;
  task_type: DocumentTaskType;
  status: DocumentTaskStatus;
  error_message: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface DocumentPreviewChunk {
  chunk_id: string;
  chunk_index: number;
  text: string;
  snippet: string;
  source_type: string | null;
  char_start: number | null;
  char_end: number | null;
  page_number: number | null;
  start_time: number | null;
  end_time: number | null;
  section_title: string | null;
  source_locator: SourceLocator | null;
  preview_target: PreviewTarget | null;
  heading_path: string[] | null;
}

export interface DocumentPreview {
  document: Document;
  chunks: DocumentPreviewChunk[];
}

export type DocumentStatusCheckState =
  | "ready"
  | "missing"
  | "warning"
  | "failed"
  | "optional"
  | "pending";

export interface DocumentStatusCheck {
  name: string;
  label: string;
  status: DocumentStatusCheckState;
  count: number | null;
  message: string;
}

export interface DocumentStatus {
  document_id: number;
  kb_id: number;
  filename: string;
  processing_status: DocumentProcessingStatus;
  rag_ready: boolean;
  block_count: number;
  chunk_count: number;
  citation_unit_count: number;
  vector_index_status: DocumentStatusCheckState;
  vector_index_count: number;
  vector_index_compatible: boolean | null;
  graph_index_status: DocumentStatusCheckState;
  entity_count: number;
  relation_count: number;
  latest_processing_job_step: string | null;
  latest_processing_job_status: ProcessingJobStatus | null;
  latest_processing_job_id: number | null;
  latest_processing_job_attempt_count: number | null;
  latest_processing_job_max_attempts: number | null;
  latest_processing_job_can_retry: boolean;
  latest_processing_job_error_code: string | null;
  latest_processing_job_error_message: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  last_indexed_at: string | null;
  warnings: string[];
  checks: DocumentStatusCheck[];
}

export interface CitationLike {
  citation_id?: number | null;
  citation_marker?: string | null;
  citation_unit_id?: number | null;
  chunk_db_id?: number | null;
  chunk_id?: string | null;
  document_id?: number | null;
  knowledge_base_id?: number | null;
  scope?: string | null;
  team_id?: number | null;
  document_name: string | null;
  snippet: string | null;
  text: string;
  source_type: string | null;
  char_start: number | null;
  char_end: number | null;
  page_number: number | null;
  start_time: number | null;
  end_time: number | null;
  section_title: string | null;
  source_locator: SourceLocator | null;
  preview_target: PreviewTarget | null;
  heading_path: string[];
  citation_ready?: boolean;
  retrieval_mode?: RetrievalMode | null;
  score?: number | null;
}

export type SourceLocatorKind =
  | "text_range"
  | "pdf_page"
  | "image_region"
  | "time_range"
  | "unknown";

export interface SourceLocator {
  kind: SourceLocatorKind;
  document_id?: number | null;
  source_type: string | null;
  source_locator_text: string | null;
  char_start: number | null;
  char_end: number | null;
  section_title: string | null;
  heading_path: string[];
  page_number: number | null;
  page_region: Record<string, unknown> | null;
  bbox: Record<string, unknown> | null;
  region_hint: string | null;
  ocr_provider: string | null;
  start_time: number | null;
  end_time: number | null;
}

export interface PreviewTarget {
  kind: "document_preview";
  document_id?: number | null;
  source_type: string | null;
  locator_kind: SourceLocatorKind;
  source_locator_text: string | null;
  char_start: number | null;
  char_end: number | null;
  section_title: string | null;
  page_number: number | null;
  start_time: number | null;
  end_time: number | null;
}

export interface RetrievalResult extends CitationLike {
  chunk_id: string;
  document_id: number;
  knowledge_base_id: number;
  scope: string;
  team_id: number | null;
  score: number;
  vector_score?: number | null;
  keyword_score?: number | null;
  graph_score?: number | null;
  matched_terms?: string[] | null;
  candidate_sources?: string[] | null;
}

export interface RetrievalResponse {
  query: string;
  top_k: number;
  mode?: RetrievalMode | null;
  requested_mode?: RetrievalMode | null;
  selected_mode?: RetrievalMode | null;
  router_reason?: string | null;
  used_reranker?: boolean | null;
  trace_id?: number | string | null;
  results: RetrievalResult[];
}

export type Citation = CitationContract;
export type AskResponse = AskResponseContract;

export interface KnowledgeGraphEntitySummary {
  id: number;
  name: string;
  entity_type: string | null;
  description: string | null;
  mention_count: number;
  relation_count: number;
}

export interface KnowledgeGraphEntityList {
  items: KnowledgeGraphEntitySummary[];
}

export interface KnowledgeGraphMention {
  document_id: number;
  document_name: string | null;
  chunk_id: number | null;
  citation_unit_id: number | null;
  source_locator: string | null;
  text_span: string | null;
}

export interface KnowledgeGraphRelation {
  id: number;
  source_entity_id: number;
  source_entity_name: string;
  target_entity_id: number;
  target_entity_name: string;
  relation_type: string;
  description: string | null;
  source_document_id: number | null;
  source_document_name: string | null;
  source_chunk_id: number | null;
  source_citation_unit_id: number | null;
  source_locator: string | null;
  confidence: number | null;
}

export interface KnowledgeGraphEntityDetail extends KnowledgeGraphEntitySummary {
  mentions: KnowledgeGraphMention[];
  relations: KnowledgeGraphRelation[];
}

export interface KnowledgeGraphExportEntity {
  id: number;
  name: string;
  entity_type: string | null;
  mention_count: number;
  relation_count: number;
}

export interface KnowledgeGraphExportSource {
  document_id: number | null;
  filename: string | null;
  chunk_id: number | null;
  citation_unit_id: number | null;
  snippet: string | null;
}

export interface KnowledgeGraphExportRelation {
  id: number;
  source_entity: string;
  target_entity: string;
  source_entity_id: number;
  target_entity_id: number;
  type: string;
  label: string | null;
  source_count: number;
  sources: KnowledgeGraphExportSource[];
}

export interface KnowledgeGraphExport {
  kb_id: number;
  total_entities: number;
  total_relations: number;
  filtered_entities: number;
  filtered_relations: number;
  available_relation_types: string[];
  entities: KnowledgeGraphExportEntity[];
  relations: KnowledgeGraphExportRelation[];
}

export interface KnowledgeGraphExportParams {
  q?: string;
  relation_type?: string;
  entity_id?: number | null;
  limit_entities?: number;
  limit_relations?: number;
  limit_sources_per_relation?: number;
}

export interface ConversationSummary {
  id: number;
  knowledge_base_id: number;
  title: string;
  scope: KnowledgeBaseScope;
  team_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: number;
  role: MessageRole;
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface Conversation extends ConversationSummary {
  messages: ConversationMessage[];
}

export interface AppendConversationMessageResponse {
  conversation: ConversationSummary;
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
}
