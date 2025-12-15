from fastapi import Request, Depends
from app.services.rag_chat import RAGService


def get_rag_service(request: Request) -> RAGService:
    return request.app.state.rag_service
