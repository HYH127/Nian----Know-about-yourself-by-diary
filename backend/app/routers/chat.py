from typing import Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.chat import chat_stream, create_session, list_sessions, get_session_messages, delete_session, rename_session

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str = ""
    retrieval_mode: Literal["rag", "entity", "both"] = "both"
    enable_web_search: bool = False


@router.post("/chat")
async def chat(request: ChatRequest):
    """SSE 流式对话"""
    session_id = request.session_id
    if not session_id:
        session_id = await create_session()

    return StreamingResponse(
        chat_stream(
            session_id,
            request.message,
            retrieval_mode=request.retrieval_mode,
            enable_web_search=request.enable_web_search,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions")
async def get_sessions():
    """获取会话列表"""
    sessions = await list_sessions()
    return sessions


@router.post("/sessions")
async def new_session():
    """创建新会话"""
    session_id = await create_session()
    return {"id": session_id, "session_id": session_id}


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str):
    """获取会话消息"""
    try:
        messages = await get_session_messages(session_id)
        return messages
    except Exception:
        return []


class RenameRequest(BaseModel):
    title: str


@router.delete("/sessions/{session_id}")
async def api_delete_session(session_id: str):
    """删除会话及其所有消息"""
    await delete_session(session_id)
    return {"status": "ok"}


@router.patch("/sessions/{session_id}")
async def api_rename_session(session_id: str, request: RenameRequest):
    try:
        await rename_session(session_id, request.title)
    except Exception:
        pass
    return {"status": "ok"}
