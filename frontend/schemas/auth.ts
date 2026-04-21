import { z } from "zod";

export const loginSchema = z.object({
  identifier: z.string().min(1, "Email or username is required."),
  password: z.string().min(8, "Password must be at least 8 characters.")
});

export const registerSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  username: z.string().min(3, "Username must be at least 3 characters."),
  password: z.string().min(8, "Password must be at least 8 characters.")
});

export type LoginFormValues = z.infer<typeof loginSchema>;
export type RegisterFormValues = z.infer<typeof registerSchema>;
