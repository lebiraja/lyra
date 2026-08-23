import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import {
  serverEventSchema,
  type ConversationState,
  type Message,
} from '@/types/protocol';

const SESSION_KEY = 'medusa.session';

export interface ChatLine {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

interface Conversation {
  state: ConversationState;
  lines: ChatLine[];
  /** Assistant text currently streaming in (not yet in `lines`). */
  streaming: string;
  sessionId: string | null;
  persona: string | null;
  error: string | null;
  currentEmotion: { label: string; confidence: number } | null;
  /** Connect and open a brand-new conversation under the given persona. */
  start: (persona: string) => void;
  sendAudio: (pcm: ArrayBuffer) => void;
  sendText: (text: string) => void;
  setMuted: (muted: boolean) => void;
  /** Open an existing saved conversation (keeps its persona) or null for fresh-default. */
  switchSession: (sessionId: string | null, persona?: string) => Promise<void>;
  sendVideoFrame: (base64: string) => void;
}

interface ConversationCallbacks {
  onAudio: (pcm: ArrayBuffer) => void;
  onInterrupted: () => void;
}

let lineId = 0;
const nextId = () => `line-${++lineId}`;

export function useConversation({ onAudio, onInterrupted }: ConversationCallbacks): Conversation {
  const [state, setState] = useState<ConversationState>('idle');
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [streaming, setStreaming] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [persona, setPersona] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [currentEmotion, setCurrentEmotion] = useState<{ label: string; confidence: number } | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<number | undefined>(undefined);
  const callbacksRef = useRef({ onAudio, onInterrupted });
  callbacksRef.current = { onAudio, onInterrupted };
  const streamingRef = useRef('');
  // What to open once the socket is ready. {session_id, persona}.
  const pendingRef = useRef<{ session_id: string | null; persona: string | null }>({
    session_id: null,
    persona: null,
  });

  const loadHistory = useCallback(async (id: string) => {
    try {
      const messages: Message[] = await api.getMessages(id);
      setLines(messages.map((m) => ({ id: nextId(), role: m.role, content: m.content })));
    } catch {
      setLines([]);
    }
  }, []);

  const connect = useCallback(() => {
    const existing = wsRef.current;
    if (existing && (existing.readyState === WebSocket.OPEN || existing.readyState === WebSocket.CONNECTING)) {
      return;
    }
    setState('connecting');

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/chat`);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      setError(null);
      const pending = pendingRef.current;
      // Reconnect with no explicit intent → resume last saved session.
      const session_id = pending.session_id ?? localStorage.getItem(SESSION_KEY);
      ws.send(
        JSON.stringify({ type: 'set_session', session_id, persona: pending.persona })
      );
    };

    ws.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        callbacksRef.current.onAudio(event.data);
        return;
      }
      const parsed = serverEventSchema.safeParse(JSON.parse(event.data as string));
      if (!parsed.success) return;
      const msg = parsed.data;

      switch (msg.type) {
        case 'session':
          setSessionId(msg.session_id);
          if (msg.persona) setPersona(msg.persona);
          localStorage.setItem(SESSION_KEY, msg.session_id);
          void loadHistory(msg.session_id);
          break;
        case 'state':
          setState(msg.state);
          break;
        case 'user_transcript':
          setCurrentEmotion(null); // Reset emotion state on new user speech
          setLines((prev) => [...prev, { id: nextId(), role: 'user', content: msg.text }]);
          break;
        case 'assistant_delta':
        case 'assistant_greeting':
          streamingRef.current += msg.text;
          setStreaming(streamingRef.current);
          break;
        case 'assistant_done':
          streamingRef.current = '';
          setStreaming('');
          setLines((prev) => [...prev, { id: nextId(), role: 'assistant', content: msg.text }]);
          break;
        case 'interrupted':
          if (streamingRef.current) {
            const partial = streamingRef.current;
            setLines((prev) => [...prev, { id: nextId(), role: 'assistant', content: partial }]);
          }
          streamingRef.current = '';
          setStreaming('');
          callbacksRef.current.onInterrupted();
          break;
        case 'emotion':
          setCurrentEmotion({ label: msg.label, confidence: msg.confidence });
          break;
        case 'error':
          setError(msg.message);
          break;
      }
    };

    ws.onclose = () => {
      setState('idle');
      if (wsRef.current === ws) {
        reconnectRef.current = window.setTimeout(connect, 2000);
      }
    };
  }, [loadHistory]);

  useEffect(() => {
    return () => {
      clearTimeout(reconnectRef.current);
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close(1000);
    };
  }, []);

  const sendAudio = useCallback((pcm: ArrayBuffer) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) ws.send(pcm);
  }, []);

  const sendVideoFrame = useCallback((base64: string) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'video_frame', data: base64 }));
    }
  }, []);

  const sendText = useCallback((text: string) => {
    const ws = wsRef.current;
    if (ws?.readyState === WebSocket.OPEN && text.trim()) {
      ws.send(JSON.stringify({ type: 'user_text', text: text.trim() }));
    }
  }, []);

  const setMuted = useCallback((muted: boolean) => {
    wsRef.current?.send(JSON.stringify({ type: 'mute', muted }));
  }, []);

  const start = useCallback(
    (chosenPersona: string) => {
      pendingRef.current = { session_id: null, persona: chosenPersona };
      localStorage.removeItem(SESSION_KEY); // fresh conversation, don't resume
      streamingRef.current = '';
      setStreaming('');
      setLines([]);
      setCurrentEmotion(null);
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        // Socket already open (e.g. picking a new persona mid-session): send now.
        ws.send(JSON.stringify({ type: 'set_session', session_id: null, persona: chosenPersona }));
      } else {
        connect();
      }
    },
    [connect]
  );

  const switchSession = useCallback(
    async (id: string | null, chosenPersona?: string) => {
      streamingRef.current = '';
      setStreaming('');
      setLines([]);
      setCurrentEmotion(null);
      pendingRef.current = { session_id: id, persona: chosenPersona ?? null };
      if (id) {
        localStorage.setItem(SESSION_KEY, id);
      } else {
        localStorage.removeItem(SESSION_KEY);
      }
      const ws = wsRef.current;
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(
          JSON.stringify({ type: 'set_session', session_id: id, persona: chosenPersona ?? null })
        );
      } else {
        connect();
      }
    },
    [connect]
  );

  return {
    state,
    lines,
    streaming,
    sessionId,
    persona,
    error,
    currentEmotion,
    start,
    sendAudio,
    sendText,
    setMuted,
    switchSession,
    sendVideoFrame,
  };
}
