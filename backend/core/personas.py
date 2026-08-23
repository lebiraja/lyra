"""Persona registry — loads conversational modes from config/personas/*.yaml.

Each persona is a distinct voice the user can choose before a conversation:
its own system prompt, voice, and behavior flags (proactive greeting,
cross-session memory). The selected persona is locked per conversation.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

PERSONAS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "personas"
DEFAULT_PERSONA = "medusa"
MEMORY_PLACEHOLDER = "{memory}"
NO_MEMORY_TEXT = "You haven't talked before yet — this is the first time. Introduce yourself warmly."


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    tagline: str
    voice: str
    proactive: bool
    cross_session_memory: bool
    system_prompt: str

    def render_prompt(self, memory: str | None = None) -> str:
        """Fill the {memory} placeholder (Friend persona); no-op for others."""
        if MEMORY_PLACEHOLDER not in self.system_prompt:
            return self.system_prompt.strip()
        text = memory.strip() if memory and memory.strip() else NO_MEMORY_TEXT
        return self.system_prompt.replace(MEMORY_PLACEHOLDER, text).strip()


class PersonaRegistry:
    def __init__(self, personas_dir: Path = PERSONAS_DIR):
        self._personas: dict[str, Persona] = {}
        for path in sorted(personas_dir.glob("*.yaml")):
            data = yaml.safe_load(path.read_text())
            persona = Persona(
                id=data["id"],
                name=data["name"],
                tagline=data.get("tagline", ""),
                voice=data.get("voice", "af_heart"),
                proactive=bool(data.get("proactive", False)),
                cross_session_memory=bool(data.get("cross_session_memory", False)),
                system_prompt=data["system_prompt"],
            )
            self._personas[persona.id] = persona

        if DEFAULT_PERSONA not in self._personas:
            raise RuntimeError(f"Default persona '{DEFAULT_PERSONA}' missing from {personas_dir}")

    def get(self, persona_id: str | None) -> Persona:
        """Return the requested persona, or the default if unknown/None."""
        return self._personas.get(persona_id or "", self._personas[DEFAULT_PERSONA])

    def exists(self, persona_id: str) -> bool:
        return persona_id in self._personas

    def list(self) -> list[dict[str, str]]:
        """Public listing for the frontend picker (Medusa first, then the rest)."""
        ordered = sorted(
            self._personas.values(),
            key=lambda p: (p.id != DEFAULT_PERSONA, p.name.lower()),
        )
        return [{"id": p.id, "name": p.name, "tagline": p.tagline} for p in ordered]
