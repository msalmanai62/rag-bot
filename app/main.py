from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
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

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Extract only the message(s) you care about
    errors = exc.errors()
    messages = [err["msg"] for err in errors]
    # Return your custom structure
    return JSONResponse(status_code=422, content={"detail": ", ".join(messages)})


if __name__ == "__main__":
    import uvicorn
    from app.settings import settings

    log.info("Starting Uvicorn server")
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
