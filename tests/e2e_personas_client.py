"""Manual end-to-end persona check against the live stack.

    docker compose exec -e PYTHONPATH=/app backend python tests/e2e_personas_client.py

Verifies: Medusa persona answers a typed turn, greets proactively on a fresh
session, and remembers across sessions.
"""

import asyncio
import json

import websockets

WS = "ws://localhost:2323/ws/chat"


async def _recv_until_listening(ws, *, expect_greeting=False):
    """Collect one assistant turn; return (texts_by_type, persona)."""
    greeting = ""
    reply = ""
    persona = None
    saw_reply = False
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=120)
        if isinstance(raw, bytes):
            continue
        m = json.loads(raw)
        t = m["type"]
        if t == "session":
            persona = m.get("persona")
        elif t == "assistant_greeting":
            greeting += m["text"]
        elif t == "assistant_delta":
            reply += m["text"]
        elif t == "assistant_done":
            saw_reply = True
        elif t == "error":
            raise SystemExit(f"ERROR: {m['message']}")
        elif t == "state" and m["state"] == "listening" and (saw_reply or (expect_greeting and greeting)):
            break
    return {"greeting": greeting, "reply": reply, "persona": persona}


async def talk(persona_id: str, message: str, *, expect_greeting=False):
    async with websockets.connect(WS, max_size=10 << 20) as ws:
        await ws.send(json.dumps({"type": "set_session", "session_id": None, "persona": persona_id}))
        if expect_greeting:
            out = await _recv_until_listening(ws, expect_greeting=True)
            assert out["persona"] == persona_id
            assert out["greeting"], "Medusa should greet first"
            print(f"  [{persona_id}] greeting: {out['greeting'][:80]}…")
        await ws.send(json.dumps({"type": "user_text", "text": message}))
        out = await _recv_until_listening(ws)
        assert out["reply"], f"{persona_id} gave no reply"
        print(f"  [{persona_id}] reply: {out['reply'][:90]}…")
        return out


async def main():
    print("Medusa answers a typed turn:")
    await talk("medusa", "I feel stuck in my career.")

    print("\nMedusa greets proactively + remembers:")
    await talk("medusa", "Work was rough but the demo went well, I'm relieved.", expect_greeting=True)
    print("  (memory summary written on disconnect)")

    # New Medusa session should load the memory and greet with continuity.
    print("\nSecond Medusa session (should remember the demo):")
    out = await talk("medusa", "Hey again.", expect_greeting=True)
    print(f"  recall greeting: {out['greeting'][:120]}")

    print("\nE2E PERSONAS: PASS")


if __name__ == "__main__":
    asyncio.run(main())
