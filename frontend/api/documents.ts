import { apiClient } from "@/lib/api-client";
import type {
  Document,
  DocumentPreview,
  DocumentTask,
  ProcessingJobSubmission
} from "@/types";

type DocumentProcessingAction = "parse" | "chunk" | "embed";

export function listPersonalDocuments(token: string, kbId: number) {
  return apiClient.get<Document[]>(`/knowledge-bases/${kbId}/documents`, token);
}

export function getPersonalDocumentPreview(
  token: string,
  kbId: number,
  documentId: number
) {
  return apiClient.get<DocumentPreview>(
    `/knowledge-bases/${kbId}/documents/${documentId}/preview`,
    token
  );
}

export function getPersonalDocumentFile(
  token: string,
  kbId: number,
  documentId: number
) {
  return apiClient.getBlob(
    `/knowledge-bases/${kbId}/documents/${documentId}/file`,
    token
  );
}

export function uploadPersonalDocument(token: string, kbId: number, file: File) {
  return apiClient.upload<Document>(`/knowledge-bases/${kbId}/documents`, file, token);
}

export function listTeamDocuments(token: string, teamId: number, kbId: number) {
  return apiClient.get<Document[]>(`/teams/${teamId}/knowledge-bases/${kbId}/documents`, token);
}

export function getTeamDocumentPreview(
  token: string,
  teamId: number,
  kbId: number,
  documentId: number
) {
  return apiClient.get<DocumentPreview>(
    `/teams/${teamId}/knowledge-bases/${kbId}/documents/${documentId}/preview`,
    token
  );
}

export function getTeamDocumentFile(
  token: string,
  teamId: number,
  kbId: number,
  documentId: number
) {
  return apiClient.getBlob(
    `/teams/${teamId}/knowledge-bases/${kbId}/documents/${documentId}/file`,
    token
  );
}

export function uploadTeamDocument(
  token: string,
  teamId: number,
  kbId: number,
  file: File
) {
  return apiClient.upload<Document>(
    `/teams/${teamId}/knowledge-bases/${kbId}/documents`,
    file,
    token
  );
}

export function listTeamReviewTasks(token: string, teamId: number) {
  return apiClient.get<Document[]>(`/teams/${teamId}/review-tasks`, token);
}

export function approveTeamDocument(token: string, teamId: number, documentId: number) {
  return apiClient.post<Document>(`/teams/${teamId}/documents/${documentId}/approve`, {}, token);
}

export function rejectTeamDocument(
  token: string,
  teamId: number,
  documentId: number,
  payload: { review_comment: string }
) {
  return apiClient.post<Document>(
    `/teams/${teamId}/documents/${documentId}/reject`,
    payload,
    token
  );
}

export function createPersonalTask(
  token: string,
  kbId: number,
  documentId: number,
  taskType: "parse" | "chunk" | "embed" | "index"
) {
  return apiClient.post<DocumentTask>(
    `/knowledge-bases/${kbId}/documents/${documentId}/${taskType}-tasks`,
    {},
    token
  );
}

export function createTeamTask(
  token: string,
  teamId: number,
  kbId: number,
  documentId: number,
  taskType: "parse" | "chunk" | "embed" | "index"
) {
  return apiClient.post<DocumentTask>(
    `/teams/${teamId}/knowledge-bases/${kbId}/documents/${documentId}/${taskType}-tasks`,
    {},
    token
  );
}

export function getDocumentTask(token: string, taskId: number) {
  return apiClient.get<DocumentTask>(`/document-tasks/${taskId}`, token);
}

export function processPersonalDocumentStep(
  token: string,
  kbId: number,
  documentId: number,
  action: DocumentProcessingAction
) {
  return apiClient.post(
    `/knowledge-bases/${kbId}/documents/${documentId}/${action}`,
    {},
    token
  );
}

export function processPersonalDocument(
  token: string,
  kbId: number,
  documentId: number
) {
  return apiClient.post<ProcessingJobSubmission>(
    `/knowledge-bases/${kbId}/documents/${documentId}/process`,
    {},
    token
  );
}

export function processTeamDocumentStep(
  token: string,
  teamId: number,
  kbId: number,
  documentId: number,
  action: DocumentProcessingAction
) {
  return apiClient.post(
    `/teams/${teamId}/knowledge-bases/${kbId}/documents/${documentId}/${action}`,
    {},
    token
  );
}

export function processTeamDocument(
  token: string,
  teamId: number,
  kbId: number,
  documentId: number
) {
  return apiClient.post<ProcessingJobSubmission>(
    `/teams/${teamId}/knowledge-bases/${kbId}/documents/${documentId}/process`,
    {},
    token
  );
}
