import { z } from "zod";

import { citationSchema } from "@/schemas/qa";

export const conversationFilterSchema = z.object({
  scope: z.enum(["all", "personal", "team"]).default("all")
});

export const conversationSummarySchema = z.object({
  id: z.number().int().positive(),
  knowledge_base_id: z.number().int().positive(),
  title: z.string(),
  scope: z.enum(["personal", "team"]),
  team_id: z.number().int().positive().nullable(),
  created_at: z.string(),
  updated_at: z.string()
});

export const conversationMessageSchema = z.object({
  id: z.number().int().positive(),
  role: z.enum(["system", "user", "assistant"]),
  content: z.string(),
  citations: z.array(citationSchema),
  created_at: z.string()
});

export const conversationSchema = conversationSummarySchema.extend({
  messages: z.array(conversationMessageSchema)
});

export const appendConversationMessageResponseSchema = z.object({
  conversation: conversationSummarySchema,
  user_message: conversationMessageSchema,
  assistant_message: conversationMessageSchema
});

export type ConversationFilterValues = z.infer<typeof conversationFilterSchema>;
