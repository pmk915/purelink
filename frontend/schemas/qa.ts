import { z } from "zod";

export const retrievalSchema = z.object({
  query: z.string().min(1, "Query is required."),
  top_k: z.coerce.number().min(1).max(20).default(5),
  mode: z.enum(["chunk_only", "overview", "graph_vector_mix", "hybrid_text"]).default("chunk_only")
});

export const askSchema = z.object({
  question: z.string().min(1, "Question is required."),
  top_k: z.coerce.number().min(1).max(20).default(5),
  conversation_id: z.number().nullable().optional()
});

export type RetrievalValues = z.infer<typeof retrievalSchema>;
export type AskValues = z.infer<typeof askSchema>;
