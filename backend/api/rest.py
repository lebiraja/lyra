"""REST endpoints: health + session management."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    app = request.app
    llm_ok = await app.state.llm.healthy()
    memory_ok = (
        await app.state.graph_store.healthy()
        if getattr(app.state, "graph_store", None) is not None
        else None
    )
    return {
        "status": "healthy" if app.state.ready and llm_ok else "degraded",
        "engines_loaded": app.state.ready,
        "llm_reachable": llm_ok,
        "semantic_memory_reachable": memory_ok,
        "latency_ms": app.state.stats.last,
    }


@router.get("/personas")
async def list_personas(request: Request):
    """The conversational modes the user can choose before a conversation."""
    return {"personas": request.app.state.personas.list()}


@router.get("/sessions")
async def list_sessions(request: Request):
    return {"sessions": await request.app.state.store.list_sessions()}


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, request: Request):
    store = request.app.state.store
    if not await store.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "messages": await store.get_messages(session_id)}


@router.get("/sessions/{session_id}/events")
async def get_events(session_id: str, request: Request):
    store = request.app.state.store
    if not await store.session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "events": await store.get_events(session_id)}


@router.get("/memory/artifacts")
async def list_memory_artifacts(request: Request):
    store = request.app.state.store
    return {
        "artifacts": await store.list_memory_artifacts(limit=100),
    }


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    if not await request.app.state.store.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": session_id}
