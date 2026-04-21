export type KnowledgeBaseScope = "personal" | "team";
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
  | "parsed"
  | "indexed"
  | "failed";
export type DocumentTaskType = "parse" | "chunk" | "embed" | "index";
export type DocumentTaskStatus = "pending" | "processing" | "succeeded" | "failed";
export type MessageRole = "system" | "user" | "assistant";

export interface ApiErrorPayload {
  detail?: string;
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
  storage_path: string;
  review_status: DocumentReviewStatus;
  processing_status: DocumentProcessingStatus;
  reviewed_by: number | null;
  reviewed_at: string | null;
  review_comment: string | null;
  created_at: string;
  updated_at: string;
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

export interface RetrievalResult {
  chunk_id: string;
  document_id: number;
  knowledge_base_id: number;
  scope: string;
  team_id: number | null;
  text: string;
  score: number;
}

export interface RetrievalResponse {
  query: string;
  top_k: number;
  results: RetrievalResult[];
}

export interface Citation {
  chunk_id: string;
  document_id: number;
  knowledge_base_id: number;
  scope: string;
  team_id: number | null;
  text: string;
}

export interface AskResponse {
  conversation_id: number;
  answer: string;
  citations: Citation[];
}

export interface ConversationSummary {
  id: number;
  knowledge_base_id: number;
  title: string;
  scope: string;
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
