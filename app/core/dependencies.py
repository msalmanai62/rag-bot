from fastapi import Request
from app.services.rag_chat import RAGService


def get_rag_service(request: Request = None) -> RAGService:
    """Get RAG service from app state. Works for both HTTP and WebSocket requests."""
    if request is None:
        # For cases where we need to pass app directly
        raise ValueError("Request is required to get RAG service")
    return request.app.state.rag_service
