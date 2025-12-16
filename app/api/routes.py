from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
import asyncio
import os
import tempfile
from pathlib import Path

from app.schemas.app_schemas import (
    CreateChatRequest,
    CreateChatResponse,
    ListChatsResponse,
    AddDocumentRequest,
    HistoryResponse,
)
from app.core.dependencies import get_rag_service
from app.utils.logger_setup import log

router = APIRouter()


@router.post("/chats", response_model=CreateChatResponse)
async def create_chat(payload: CreateChatRequest, rag_service=Depends(get_rag_service)):
    chat_id = rag_service.create_chat(payload.user_id, name=payload.name, create_with_default_docs=False)
    if payload.default_url:
        # add docs asynchronously
        asyncio.create_task(asyncio.to_thread(rag_service.add_documents_from_url, payload.user_id, chat_id, payload.default_url))
    return CreateChatResponse(user_id=payload.user_id, chat_id=chat_id)


@router.get("/chats/{user_id}", response_model=ListChatsResponse)
async def list_chats(user_id: str, rag_service=Depends(get_rag_service)):
    chats = rag_service.list_chats(user_id)
    return ListChatsResponse(chats=chats)


@router.post("/chats/add_document")
async def add_document(req: AddDocumentRequest, rag_service=Depends(get_rag_service)):
    if not rag_service.ensure_chat_exists_for_user(req.user_id, req.chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    if req.url:
        rag_service.add_documents_from_url(req.user_id, req.chat_id, req.url)
    return JSONResponse({"status": "ok"})


@router.post("/chats/add_file")
async def add_file(
    user_id: str = Form(...),
    chat_id: str = Form(...),
    file: UploadFile = File(...),
    rag_service=Depends(get_rag_service)
):
    """
    Upload and process a document file (PDF, DOCX, CSV, TXT).
    
    Args:
        user_id: User ID
        chat_id: Chat ID
        file: The uploaded file
        
    Returns:
        Status response with file information
    """
    # Validate file type
    allowed_extensions = {'.pdf', '.docx', '.csv', '.txt', '.text'}
    file_ext = Path(file.filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. Supported types: pdf, docx, csv, txt"
        )
    
    # Validate file size (max 10MB)
    max_size = 10 * 1024 * 1024
    file_size = len(await file.read())
    await file.seek(0)  # Reset file pointer
    
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: 10MB, received: {file_size / 1024 / 1024:.2f}MB"
        )
    
    # Check if chat exists
    if not rag_service.ensure_chat_exists_for_user(user_id, chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Save uploaded file to temporary location
    temp_dir = tempfile.gettempdir()
    temp_file_path = os.path.join(temp_dir, f"rag_upload_{chat_id}_{file.filename}")
    
    try:
        # Save file
        contents = await file.read()
        with open(temp_file_path, "wb") as f:
            f.write(contents)
        
        log.info(f"Processing file upload: {file.filename} for chat {chat_id}")
        
        # Process file in background thread
        await asyncio.to_thread(
            rag_service.add_documents_from_file,
            user_id,
            chat_id,
            temp_file_path,
            file.filename
        )
        
        return JSONResponse({
            "status": "ok",
            "message": f"File '{file.filename}' uploaded and processed successfully",
            "file_name": file.filename,
            "file_size": file_size
        })
        
    except ValueError as e:
        # File type not supported
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error(f"Error processing file upload: {e}")
        # Clean up temp file on error
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.get("/history/{user_id}/{chat_id}", response_model=HistoryResponse)
async def history(user_id: str, chat_id: str, rag_service=Depends(get_rag_service)):
    msgs = rag_service.get_history(user_id, chat_id)
    return HistoryResponse(messages=msgs)


@router.delete("/chats/{user_id}/{chat_id}")
async def delete_chat(user_id: str, chat_id: str, rag_service=Depends(get_rag_service)):
    try:
        rag_service.delete_chat(user_id, chat_id)
        return JSONResponse({"status": "ok", "message": "Chat deleted successfully"})
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.websocket("/ws/{user_id}/{chat_id}")
async def websocket_chat(websocket: WebSocket, user_id: str, chat_id: str):
    """WebSocket endpoint for real-time chat streaming."""
    print(f"WebSocket connection attempt: user_id={user_id}, chat_id={chat_id}")
    
    try:
        await websocket.accept()
        print("WebSocket connection accepted")
    except Exception as e:
        print(f"Failed to accept WebSocket: {e}")
        return
    
    # Get RAG service from app state after connection is accepted
    try:
        rag_service = websocket.app.state.rag_service
        print(f"RAG service retrieved: {rag_service}")
    except Exception as e:
        print(f"Error getting RAG service: {e}")
        await websocket.send_text(f"__error__:Service initialization failed")
        await websocket.close(code=1000)
        return
    
    try:
        while True:
            # Wait for incoming message
            data = await websocket.receive_text()
            print(f"Received message: {data[:50]}...")
            
            # Stream response in background thread
            loop = asyncio.get_event_loop()
            stream_complete = asyncio.Event()

            def iter_and_send():
                try:
                    for chunk in rag_service.stream(user_id, chat_id, data):
                        try:
                            asyncio.run_coroutine_threadsafe(websocket.send_text(chunk), loop)
                        except Exception as send_err:
                            print(f"Error sending chunk: {send_err}")
                    # Send completion signal
                    asyncio.run_coroutine_threadsafe(websocket.send_text("__END__"), loop)
                except Exception as stream_err:
                    print(f"Stream error: {stream_err}")
                    asyncio.run_coroutine_threadsafe(
                        websocket.send_text(f"__error__:{str(stream_err)}"), 
                        loop
                    )
                finally:
                    stream_complete.set()

            await asyncio.to_thread(iter_and_send)
            
    except WebSocketDisconnect:
        print("WebSocket disconnected normally")
    except Exception as e:
        print(f"Unexpected WebSocket error: {e}")
        try:
            await websocket.close(code=1011)
        except:
            pass
