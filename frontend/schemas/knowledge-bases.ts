import { z } from "zod";

export const createKnowledgeBaseSchema = z.object({
  name: z.string().min(1, "Knowledge base name is required."),
  description: z.string().optional().or(z.literal(""))
});

export const updateKnowledgeBaseSchema = createKnowledgeBaseSchema.partial();

export type CreateKnowledgeBaseValues = z.infer<typeof createKnowledgeBaseSchema>;
