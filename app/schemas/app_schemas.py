from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


class CreateChatRequest(BaseModel):
    user_email: EmailStr
    name: Optional[str] = None
    default_url: Optional[str] = None


class CreateChatResponse(BaseModel):
    user_email: EmailStr
    chat_id: str


class ListChatsResponseItem(BaseModel):
    chat_id: str
    name: Optional[str]
    created_at: str


class ListChatsResponse(BaseModel):
    chats: List[ListChatsResponseItem]


class AddDocumentRequest(BaseModel):
    user_email: EmailStr
    chat_id: str
    url: Optional[str]


class MessageItem(BaseModel):
    role: str
    content: str
    created_at: str


class HistoryResponse(BaseModel):
    messages: List[MessageItem]
