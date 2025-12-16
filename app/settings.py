from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    GOOGLE_API_KEY: str
    CHROMA_BASE_DIR: str = "chroma_langchain_db"
    SQLITE_PATH: str = "rag_manager.sqlite"
    MODEL_NAME: str = "google_genai:gemini-2.5-flash-lite"
    JWT_SECRET: str = "change-me"
    JWT_ALGORITHM: str = "HS256"
    HOST: str = "0.0.0.0"
    PORT: int = 8001

    class Config:
        env_file = ".env"


settings = Settings()
