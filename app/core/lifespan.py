from contextlib import asynccontextmanager
from app.services.rag_chat import RAGService
from app.settings import settings
from app.utils.logger_setup import log


@asynccontextmanager
async def lifespan(app):
    log.info("Starting application and RAG service")
    rag = RAGService(
        default_page_url=None,
        chroma_base_dir=settings.CHROMA_BASE_DIR,
        sqlite_path=settings.SQLITE_PATH,
        model_name=settings.MODEL_NAME,
    )
    app.state.rag_service = rag
    try:
        yield
    finally:
        log.info("Shutting down application")
