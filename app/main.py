from fastapi import FastAPI
from app.api.router import api_router
from app.core.lifespan import lifespan
from app.core.cors_handler import add_cors
from app.utils.logger_setup import log


def create_app():
    app = FastAPI(lifespan=lifespan)
    add_cors(app)
    app.include_router(api_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    from app.settings import settings

    log.info("Starting Uvicorn server")
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
