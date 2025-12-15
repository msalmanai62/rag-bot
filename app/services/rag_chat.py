import os
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Generator, Optional, List

from dotenv import load_dotenv
from langchain_community.document_loaders import WebBaseLoader
from langchain.chat_models import init_chat_model
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.agents.middleware import dynamic_prompt, ModelRequest
from langchain.agents import create_agent
from langgraph.checkpoint.sqlite import SqliteSaver

from app.utils.logger_setup import log


class RAGService:
    """Adapted RAG manager to be used as an application service."""

    def __init__(
        self,
        default_page_url: Optional[str] = None,
        chroma_base_dir: str = "chroma_langchain_db",
        sqlite_path: str = "rag_manager.sqlite",
        model_name: str = "google_genai:gemini-2.5-flash-lite",
    ):
        load_dotenv()
        if not os.environ.get("GOOGLE_API_KEY"):
            log.warning("GOOGLE_API_KEY not found in environment; embedding/init may fail in tests")

        self.default_page_url = default_page_url
        self.chroma_base_dir = Path(chroma_base_dir)
        self.chroma_base_dir.mkdir(parents=True, exist_ok=True)

        # Single shared model and embedding function
        self.model = init_chat_model(model_name)
        self.embedding_function = GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001"
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200, add_start_index=True
        )

        # In-memory caches
        self.vectorstores: Dict[Tuple[str, str], Chroma] = {}
        self.agents: Dict[Tuple[str, str], object] = {}
        self.dynamic_prompts: Dict[Tuple[str, str], object] = {}
        self.locks: Dict[Tuple[str, str], threading.Lock] = {}

        # SQLite for persistent metadata and messages + agent checkpointer
        self.conn = sqlite3.connect(sqlite_path, check_same_thread=False)
        self._init_sqlite()
        self.checkpointer = SqliteSaver(conn=self.conn)

        # thread-safety for DB access
        self.db_lock = threading.Lock()

    def _init_sqlite(self):
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                chat_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def create_chat(self, user_id: str, name: Optional[str] = None, create_with_default_docs: bool = False) -> str:
        chat_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with self.db_lock:
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO chats (chat_id, user_id, name, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, user_id, name or "", now),
            )
            self.conn.commit()

        # create directory for vector store
        self._init_vectorstore_for_chat(user_id, chat_id)

        if create_with_default_docs and self.default_page_url:
            self.add_documents_from_url(user_id, chat_id, self.default_page_url)

        return chat_id

    def list_chats(self, user_id: str) -> List[Dict]:
        cur = self.conn.cursor()
        cur.execute("SELECT chat_id, name, created_at FROM chats WHERE user_id = ?", (user_id,))
        rows = cur.fetchall()
        return [{"chat_id": r[0], "name": r[1], "created_at": r[2]} for r in rows]

    def get_history(self, user_id: str, chat_id: str) -> List[Dict]:
        self._assert_chat_owner(user_id, chat_id)
        cur = self.conn.cursor()
        cur.execute(
            "SELECT role, content, created_at FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,),
        )
        return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in cur.fetchall()]

    def delete_chat(self, user_id: str, chat_id: str):
        self._assert_chat_owner(user_id, chat_id)
        with self.db_lock:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            cur.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,))
            self.conn.commit()

        vs_key = (user_id, chat_id)
        if vs_key in self.vectorstores:
            try:
                del self.vectorstores[vs_key]
            except Exception:
                pass
        if vs_key in self.agents:
            del self.agents[vs_key]
        if vs_key in self.dynamic_prompts:
            del self.dynamic_prompts[vs_key]

        persist_dir = self._get_persist_dir(user_id, chat_id)
        if persist_dir.exists():
            shutil.rmtree(persist_dir)

        if vs_key in self.locks:
            del self.locks[vs_key]

    def clear_chat(self, user_id: str, chat_id: str):
        self._assert_chat_owner(user_id, chat_id)
        with self.db_lock:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
            self.conn.commit()

        persist_dir = self._get_persist_dir(user_id, chat_id)
        if persist_dir.exists():
            shutil.rmtree(persist_dir)
            persist_dir.mkdir(parents=True, exist_ok=True)

        vs_key = (user_id, chat_id)
        if vs_key in self.vectorstores:
            del self.vectorstores[vs_key]
        if vs_key in self.agents:
            del self.agents[vs_key]
        if vs_key in self.dynamic_prompts:
            del self.dynamic_prompts[vs_key]

    def _assert_chat_owner(self, user_id: str, chat_id: str):
        cur = self.conn.cursor()
        cur.execute("SELECT user_id FROM chats WHERE chat_id = ?", (chat_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Chat not found")
        if row[0] != user_id:
            raise PermissionError("User does not own this chat")

    def _get_persist_dir(self, user_id: str, chat_id: str) -> Path:
        return self.chroma_base_dir / str(user_id) / str(chat_id)

    def _init_vectorstore_for_chat(self, user_id: str, chat_id: str) -> Chroma:
        key = (user_id, chat_id)
        if key in self.vectorstores:
            return self.vectorstores[key]

        persist_dir = str(self._get_persist_dir(user_id, chat_id))
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        vs = Chroma(
            collection_name=f"{user_id}_{chat_id}",
            embedding_function=self.embedding_function,
            persist_directory=persist_dir,
        )
        self.vectorstores[key] = vs
        self.locks[key] = threading.Lock()
        return vs

    def add_documents_from_url(self, user_id: str, chat_id: str, page_url: str):
        self._assert_chat_owner(user_id, chat_id)
        vs = self._init_vectorstore_for_chat(user_id, chat_id)

        loader = WebBaseLoader(web_paths=[page_url])
        docs = loader.load()
        chunks = self.text_splitter.split_documents(docs)

        key = (user_id, chat_id)
        with self.locks.get(key, threading.Lock()):
            vs.add_documents(chunks)

    def _build_dynamic_prompt_for_chat(self, user_id: str, chat_id: str):
        key = (user_id, chat_id)
        if key in self.dynamic_prompts:
            return self.dynamic_prompts[key]

        vs = self._init_vectorstore_for_chat(user_id, chat_id)

        @dynamic_prompt
        def prompt_with_context(request: ModelRequest) -> str:
            last_query = request.state["messages"][-1].text
            retrieved_docs = vs.similarity_search(last_query, k=3)
            docs_content = "\n\n".join(doc.page_content for doc in retrieved_docs)
            system_message = (
                "You are a helpful assistant. Use the following context:\n\n"
                f"{docs_content}"
            )
            return system_message

        self.dynamic_prompts[key] = prompt_with_context
        return prompt_with_context

    def _init_agent_for_chat(self, user_id: str, chat_id: str):
        key = (user_id, chat_id)
        if key in self.agents:
            return self.agents[key]

        prompt_mw = self._build_dynamic_prompt_for_chat(user_id, chat_id)
        agent = create_agent(
            self.model,
            tools=[],
            middleware=[prompt_mw],
            checkpointer=self.checkpointer,
        )
        self.agents[key] = agent
        return agent

    def _add_message(self, user_id: str, chat_id: str, role: str, content: str):
        with self.db_lock:
            now = datetime.now().isoformat()
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO messages (chat_id, user_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, role, content, now),
            )
            self.conn.commit()

    def stream(self, user_id: str, chat_id: str, query: str, thread_id: Optional[str] = None) -> Generator[str, None, None]:
        self._assert_chat_owner(user_id, chat_id)
        agent = self._init_agent_for_chat(user_id, chat_id)

        self._add_message(user_id, chat_id, "user", query)

        assembled = []
        cfg_thread_id = thread_id or chat_id

        for token, metadata in agent.stream(
            input={"messages": [{"role": "user", "content": query}]},
            stream_mode="messages",
            config={"configurable": {"thread_id": str(cfg_thread_id)}},
        ):
            if token.content_blocks:
                text = token.content_blocks[0]["text"]
                assembled.append(text)
                yield text

        assistant_full = "".join(assembled)
        if assistant_full:
            self._add_message(user_id, chat_id, "assistant", assistant_full)

    def ensure_chat_exists_for_user(self, user_id: str, chat_id: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM chats WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        return cur.fetchone() is not None
