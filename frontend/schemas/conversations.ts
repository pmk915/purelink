import { z } from "zod";

export const conversationFilterSchema = z.object({
  scope: z.enum(["all", "personal", "team"]).default("all")
});

export type ConversationFilterValues = z.infer<typeof conversationFilterSchema>;
