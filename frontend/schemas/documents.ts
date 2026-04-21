import { z } from "zod";

export const rejectDocumentSchema = z.object({
  review_comment: z.string().min(1, "Rejection reason is required.")
});

export type RejectDocumentValues = z.infer<typeof rejectDocumentSchema>;
