import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

interface PersonaPickerProps {
  onBegin: (personaId: string) => void;
}

/** The opening screen: welcome to Medusa, the friend to share all the things. */
export function PersonaPicker({ onBegin }: PersonaPickerProps) {
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [personaId, setPersonaId] = useState('medusa');

  useEffect(() => {
    api
      .listPersonas()
      .then((list) => {
        setLoading(false);
        const medusa = list.find((p) => p.id === 'medusa') || list[0];
        if (medusa) {
          setPersonaId(medusa.id);
        }
      })
      .catch(() => {
        setLoading(false);
        setOffline(true);
      });
  }, []);

  return (
    <main className="mx-auto flex h-full max-w-md flex-col items-center justify-center gap-8 px-6">
      <div className="text-center space-y-4">
        <h1 className="font-serif text-5xl font-extralight tracking-widest text-ink transition-all duration-700 animate-pulse">
          Medusa
        </h1>
        <p className="font-serif text-sm italic tracking-wide text-ink-dim/90">
          the friend to share all the things
        </p>
      </div>

      <div className="w-full flex justify-center py-4">
        {loading ? (
          <p className="text-center text-sm text-ink-faint tracking-wider animate-pulse">connecting...</p>
        ) : offline ? (
          <p className="text-center text-sm text-ember-soft">
            Backend offline — start it and refresh.
          </p>
        ) : (
          <button
            onClick={() => onBegin(personaId)}
            className="group relative flex items-center justify-center rounded-full border border-ember-soft/40 px-12 py-4 text-ember overflow-hidden transition-all duration-300 hover:border-ember hover:bg-ember hover:text-room hover:shadow-lg hover:shadow-ember/20 active:scale-95"
          >
            <span className="relative z-10 font-serif text-lg tracking-widest">
              begin
            </span>
          </button>
        )}
      </div>

      <p className="text-center text-xs text-ink-faint tracking-wide">
        Everything stays on this machine.
      </p>
    </main>
  );
}
