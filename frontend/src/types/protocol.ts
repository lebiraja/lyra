import { z } from 'zod';

// ---- WebSocket: server -> client ----

export const serverEventSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('session'),
    session_id: z.string(),
    persona: z.string().optional(),
  }),
  z.object({
    type: z.literal('state'),
    state: z.enum(['listening', 'transcribing', 'generating', 'speaking']),
  }),
  z.object({
    type: z.literal('user_transcript'),
    text: z.string(),
    language: z.string().optional(),
    language_probability: z.number().optional(),
  }),
  z.object({ type: z.literal('assistant_delta'), text: z.string() }),
  z.object({ type: z.literal('assistant_greeting'), text: z.string() }),
  z.object({ type: z.literal('assistant_done'), text: z.string() }),
  z.object({ type: z.literal('interrupted') }),
  z.object({
    type: z.literal('emotion'),
    label: z.string(),
    confidence: z.number(),
    source: z.string().optional(),
  }),
  z.object({ type: z.literal('error'), message: z.string() }),
]);

export type ServerEvent = z.infer<typeof serverEventSchema>;
export type ConversationState =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'transcribing'
  | 'generating'
  | 'speaking';

// ---- REST ----

export const personaSchema = z.object({
  id: z.string(),
  name: z.string(),
  tagline: z.string(),
});

export const personasResponseSchema = z.object({ personas: z.array(personaSchema) });

export const sessionSchema = z.object({
  id: z.string(),
  title: z.string(),
  persona: z.string().optional(),
  created_at: z.string(),
  message_count: z.number(),
});

export const messageSchema = z.object({
  role: z.enum(['user', 'assistant']),
  content: z.string(),
  created_at: z.string(),
});

export const sessionsResponseSchema = z.object({ sessions: z.array(sessionSchema) });
export const messagesResponseSchema = z.object({
  session_id: z.string(),
  messages: z.array(messageSchema),
});

export type Persona = z.infer<typeof personaSchema>;
export type Session = z.infer<typeof sessionSchema>;
export type Message = z.infer<typeof messageSchema>;
