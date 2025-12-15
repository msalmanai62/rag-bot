from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import asyncio

from app.schemas.app_schemas import (
    CreateChatRequest,
    CreateChatResponse,
    ListChatsResponse,
    AddDocumentRequest,
    HistoryResponse,
)
from app.core.dependencies import get_rag_service

router = APIRouter()


@router.post("/chats", response_model=CreateChatResponse)
def create_chat(payload: CreateChatRequest, rag_service=Depends(get_rag_service)):
    chat_id = rag_service.create_chat(payload.user_email, name=payload.name, create_with_default_docs=False)
    if payload.default_url:
        # add docs asynchronously
        asyncio.create_task(asyncio.to_thread(rag_service.add_documents_from_url, payload.user_email, chat_id, payload.default_url))
    return CreateChatResponse(user_email=payload.user_email, chat_id=chat_id)


@router.get("/chats/{user_email}", response_model=ListChatsResponse)
def list_chats(user_email: str, rag_service=Depends(get_rag_service)):
    chats = rag_service.list_chats(user_email)
    return ListChatsResponse(chats=chats)


@router.post("/chats/add_document")
def add_document(req: AddDocumentRequest, rag_service=Depends(get_rag_service)):
    if not rag_service.ensure_chat_exists_for_user(req.user_email, req.chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    if req.url:
        rag_service.add_documents_from_url(req.user_email, req.chat_id, req.url)
    return JSONResponse({"status": "ok"})


@router.get("/history/{user_email}/{chat_id}", response_model=HistoryResponse)
def history(user_email: str, chat_id: str, rag_service=Depends(get_rag_service)):
    msgs = rag_service.get_history(user_email, chat_id)
    return HistoryResponse(messages=msgs)


@router.websocket("/ws/{user_email}/{chat_id}")
async def websocket_chat(websocket: WebSocket, user_email: str, chat_id: str, rag_service=Depends(get_rag_service)):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # stream in background thread and forward to websocket
            loop = asyncio.get_event_loop()

            def iter_and_send():
                try:
                    for chunk in rag_service.stream(user_email, chat_id, data):
                        asyncio.run_coroutine_threadsafe(websocket.send_text(chunk), loop)
                except Exception as e:
                    asyncio.run_coroutine_threadsafe(websocket.send_text(f"__error__:{str(e)}"), loop)

            await asyncio.to_thread(iter_and_send)
    except WebSocketDisconnect:
        return
