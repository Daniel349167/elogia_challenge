import os
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.api.chat import router as chat_router
from app.api.insights import router as insights_router
from app.api.receipts import router as receipts_router
from app.config import get_settings
from app.db import init_db

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "http_error",
                "message": str(exc.detail),
                "status_code": exc.status_code,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "request_validation_error",
                "message": "Request validation failed",
                "detail": exc.errors(),
            }
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(_: Request, exc: Exception) -> JSONResponse:
    error_id = str(uuid.uuid4())
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Unexpected server error",
                "error_id": error_id,
                "detail": "See server logs with error_id",
            }
        },
    )


@app.on_event("startup")
def startup() -> None:
    os.makedirs(settings.upload_dir, exist_ok=True)
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(chat_router)
app.include_router(receipts_router)
app.include_router(insights_router)
