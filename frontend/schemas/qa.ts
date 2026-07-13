import { z } from "zod";

export const retrievalModeSchema = z.enum([
  "auto",
  "chunk_only",
  "overview",
  "graph_vector_mix",
  "hybrid_text"
]);

const nullableString = z.string().nullish().default(null);
const nullableNumber = z.number().finite().nullish().default(null);
const nullableId = z.number().int().positive().nullish().default(null);
const headingPathSchema = z.preprocess(
  (value) => value ?? [],
  z.array(z.string())
);

const sourceLocatorSchema = z.object({
  kind: z.enum(["text_range", "pdf_page", "image_region", "time_range", "unknown"]),
  document_id: nullableId,
  source_type: nullableString,
  source_locator_text: nullableString,
  char_start: nullableNumber,
  char_end: nullableNumber,
  section_title: nullableString,
  heading_path: headingPathSchema,
  page_number: nullableNumber,
  page_region: z.record(z.unknown()).nullish().default(null),
  bbox: z.record(z.unknown()).nullish().default(null),
  region_hint: nullableString,
  ocr_provider: nullableString,
  start_time: nullableNumber,
  end_time: nullableNumber
}).superRefine(validateCharRangePair);

const previewTargetSchema = z.object({
  kind: z.literal("document_preview"),
  document_id: nullableId,
  source_type: nullableString,
  locator_kind: z.enum(["text_range", "pdf_page", "image_region", "time_range", "unknown"]),
  source_locator_text: nullableString,
  char_start: nullableNumber,
  char_end: nullableNumber,
  section_title: nullableString,
  page_number: nullableNumber,
  start_time: nullableNumber,
  end_time: nullableNumber
}).superRefine(validateCharRangePair);

export const citationSchema = z.object({
  citation_id: nullableId,
  citation_marker: nullableString,
  citation_unit_id: nullableId,
  chunk_db_id: nullableId,
  chunk_id: z.string().nullish().default(null),
  document_id: nullableId,
  knowledge_base_id: nullableId,
  scope: nullableString,
  team_id: nullableId,
  document_name: nullableString,
  snippet: nullableString,
  text: z.string(),
  source_type: nullableString,
  char_start: nullableNumber,
  char_end: nullableNumber,
  page_number: nullableNumber,
  start_time: nullableNumber,
  end_time: nullableNumber,
  section_title: nullableString,
  source_locator: sourceLocatorSchema.nullish().default(null),
  preview_target: previewTargetSchema.nullish().default(null),
  heading_path: headingPathSchema,
  citation_ready: z.boolean().optional().default(false),
  retrieval_mode: retrievalModeSchema.nullish().default(null),
  score: nullableNumber
}).superRefine(validateCharRangePair);

export const askResponseSchema = z.object({
  conversation_id: z.number().int().positive(),
  answer: z.string(),
  citations: z.array(citationSchema),
  intent: nullableString,
  retrieval_mode: retrievalModeSchema.nullish().default(null),
  requested_mode: retrievalModeSchema.nullish().default(null),
  selected_mode: retrievalModeSchema.nullish().default(null),
  router_reason: nullableString,
  used_reranker: z.boolean().nullish().default(null),
  trace_id: z.union([z.number(), z.string()]).nullish().default(null)
});

export const retrievalSchema = z.object({
  query: z.string().min(1, "Query is required."),
  top_k: z.coerce.number().min(1).max(20).default(5),
  mode: retrievalModeSchema.default("auto")
});

export const askSchema = z.object({
  question: z.string().min(1, "Question is required."),
  top_k: z.coerce.number().min(1).max(20).default(5),
  conversation_id: z.number().nullable().optional(),
  mode: retrievalModeSchema.default("auto")
});

function validateCharRangePair(
  value: { char_start?: number | null; char_end?: number | null },
  context: z.RefinementCtx
) {
  const hasStart = typeof value.char_start === "number";
  const hasEnd = typeof value.char_end === "number";
  if (hasStart !== hasEnd || (hasStart && hasEnd && !(value.char_start! >= 0 && value.char_start! < value.char_end!))) {
    context.addIssue({
      code: z.ZodIssueCode.custom,
      message: "char_start and char_end must form a valid range."
    });
  }
}

export type RetrievalValues = z.infer<typeof retrievalSchema>;
export type AskValues = z.infer<typeof askSchema>;
export type CitationContract = z.infer<typeof citationSchema>;
export type AskResponseContract = z.infer<typeof askResponseSchema>;
