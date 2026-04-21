import { z } from "zod";

export const createTeamSchema = z.object({
  name: z.string().min(1, "Team name is required."),
  description: z.string().optional().or(z.literal(""))
});

export const joinTeamSchema = z.object({
  code: z.string().min(1, "Invite code is required.")
});

export const createInviteSchema = z.object({
  expires_in_days: z.coerce.number().min(1).max(365)
});

export type CreateTeamValues = z.infer<typeof createTeamSchema>;
export type JoinTeamValues = z.infer<typeof joinTeamSchema>;
export type CreateInviteValues = z.infer<typeof createInviteSchema>;
