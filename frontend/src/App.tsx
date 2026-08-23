import { useCallback, useEffect, useRef, useState } from 'react';
import { useConversation, type ChatLine } from '@/hooks/useConversation';
import { useMicStream } from '@/hooks/useMicStream';
import { usePlayback } from '@/hooks/usePlayback';
import { PersonaPicker } from '@/components/PersonaPicker';
import { SessionDrawer } from '@/components/SessionDrawer';
import { Waveform } from '@/components/Waveform';

const STATE_LABEL: Record<string, string> = {
  idle: 'offline',
  connecting: 'waking up',
  listening: 'listening',
  transcribing: 'listening',
  generating: 'thinking',
  speaking: 'speaking',
};

export default function App() {
  const [began, setBegan] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  const playback = usePlayback();
  const conversation = useConversation({
    onAudio: playback.enqueue,
    onInterrupted: playback.flush,
  });
  const mic = useMicStream(conversation.sendAudio, conversation.sendVideoFrame);

  const begin = useCallback(
    async (personaId: string) => {
      setBegan(true);
      conversation.start(personaId);
      await mic.start();
    },
    [conversation, mic]
  );

  // Keep the latest words in view
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [conversation.lines, conversation.streaming]);

  const toggleMute = () => {
    const next = !playback.muted;
    playback.setMuted(next);
    conversation.setMuted(next);
  };

  const submitDraft = () => {
    if (!draft.trim()) return;
    conversation.sendText(draft);
    setDraft('');
  };

  if (!began) {
    return <PersonaPicker onBegin={(id) => void begin(id)} />;
  }

  const status = STATE_LABEL[conversation.state] ?? '';
  const personaName = conversation.persona
    ? conversation.persona.charAt(0).toUpperCase() + conversation.persona.slice(1)
    : 'Medusa';

  return (
    <main className="mx-auto flex h-full max-w-2xl flex-col px-5">
      {/* top bar — almost nothing */}
      <header className="flex items-center justify-between py-4">
        <button
          onClick={() => setDrawerOpen(true)}
          className="text-sm text-ink-faint transition-colors hover:text-ink"
        >
          conversations
        </button>
        <span className="font-serif text-sm text-ink-dim">{personaName}</span>
        <button
          onClick={toggleMute}
          className={`text-sm transition-colors ${
            playback.muted ? 'text-ember' : 'text-ink-faint hover:text-ink'
          }`}
        >
          {playback.muted ? 'voice off' : 'voice on'}
        </button>
      </header>

      {/* the conversation */}
      <div ref={scrollRef} className="flex-1 space-y-8 overflow-y-auto py-6">
        {conversation.lines.length === 0 && !conversation.streaming && (
          <p className="pt-24 text-center text-sm text-ink-faint">
            {mic.isActive ? 'Just start talking.' : 'Type below to begin.'}
          </p>
        )}

        {conversation.lines.map((line: ChatLine) =>
          line.role === 'user' ? (
            <p key={line.id} className="text-base leading-relaxed text-ink-dim">
              <span className="text-ink-faint">— </span>
              {line.content}
            </p>
          ) : (
            <p key={line.id} className="font-serif text-lg leading-loose text-ink">
              {line.content}
            </p>
          )
        )}

        {conversation.streaming && (
          <p className="font-serif text-lg leading-loose text-ink">
            {conversation.streaming}
            <span className="animate-caret text-ember">▌</span>
          </p>
        )}
      </div>

      {/* the floor: waveform, state, input */}
      <footer className="space-y-3 pb-6">
        <Waveform
          analyser={mic.analyser}
          active={mic.isActive && (conversation.state === 'listening' || conversation.state === 'transcribing')}
        />

        <div className="flex flex-col items-center justify-center gap-1.5">
          <div className="flex items-center gap-2 text-xs tracking-widest text-ink-faint uppercase">
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                conversation.state === 'speaking'
                  ? 'animate-breathe bg-ember'
                  : conversation.state === 'generating'
                    ? 'animate-breathe bg-ink-dim'
                    : conversation.state === 'listening' || conversation.state === 'transcribing'
                      ? 'bg-ember'
                      : 'bg-ink-faint'
              }`}
            />
            {status}
          </div>
          {conversation.currentEmotion && (
            <div className="text-[10px] tracking-wider text-ink-faint/80 lowercase italic animate-pulse">
              user state: {conversation.currentEmotion.label} ({Math.round(conversation.currentEmotion.confidence * 100)}% confidence)
            </div>
          )}
        </div>

        {(mic.error ?? conversation.error) && (
          <p className="text-center text-xs text-ember-soft">{mic.error ?? conversation.error}</p>
        )}

        <div className="flex items-center gap-3 border-t border-room-line pt-4">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') submitDraft();
            }}
            placeholder="or type instead…"
            className="flex-1 bg-transparent text-sm text-ink placeholder-ink-faint outline-none"
          />
          {draft.trim() && (
            <button onClick={submitDraft} className="text-sm text-ember hover:text-ink">
              send
            </button>
          )}
        </div>
      </footer>

      <SessionDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        currentSessionId={conversation.sessionId}
        onSelect={(id, p) => void conversation.switchSession(id, p)}
        onNewConversation={() => setBegan(false)}
      />
    </main>
  );
}
