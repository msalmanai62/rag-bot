from fastapi import APIRouter
from app.api import routes

api_router = APIRouter()
api_router.include_router(routes.router, prefix="/api")
