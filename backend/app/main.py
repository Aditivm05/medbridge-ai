from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
from app.core.config import settings
from app.api.api_v1 import api_router

from contextlib import asynccontextmanager
import os
import logging
from app.core.firestore_client import is_testing_environment, ensure_emulator_storage_bucket

logger = logging.getLogger(__name__)


import re

class StreamAccessLogFilter(logging.Filter):
    """
    Ensures uvicorn's access log never prints stream tokens or query strings.
    Strips query strings from /stream requests and redacts any query containing token=.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        # 1. Standard uvicorn access record args: (client_addr, method, full_path, http_version, status_code)
        if record.args and isinstance(record.args, (tuple, list)) and len(record.args) >= 3:
            args_list = list(record.args)
            full_path = str(args_list[2])
            if "?" in full_path:
                path, query = full_path.split("?", 1)
                if "stream" in path or "token=" in query:
                    args_list[2] = path
                    record.args = tuple(args_list)

        # 2. Direct string record or pre-formatted message
        if isinstance(record.msg, str) and ("stream?" in record.msg or "token=" in record.msg):
            record.msg = re.sub(r'(/stream)\?[^\s"\'\)]*', r'\1', record.msg)
            record.msg = re.sub(r'token=[^&\s"\'\)]*', 'token=[REDACTED]', record.msg)

        return True


def setup_access_log_sanitizer():
    """Attaches StreamAccessLogFilter to uvicorn.access logger and all of its handlers."""
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, StreamAccessLogFilter) for f in access_logger.filters):
        access_logger.addFilter(StreamAccessLogFilter())
    for handler in access_logger.handlers:
        if not any(isinstance(f, StreamAccessLogFilter) for f in handler.filters):
            handler.addFilter(StreamAccessLogFilter())


setup_access_log_sanitizer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Sanitize uvicorn access logger to never print stream tokens or query strings
    setup_access_log_sanitizer()

    # 1. Startup validation: ensure DOC_STREAM_SECRET is set outside testing
    if not is_testing_environment():
        secret = os.environ.get("DOC_STREAM_SECRET") or settings.DOC_STREAM_SECRET
        if not secret or not secret.strip():
            logger.error("DOC_STREAM_SECRET is required outside testing environments.")
            raise RuntimeError("DOC_STREAM_SECRET environment variable is required outside testing environments.")

    # 2. Startup: Ensure storage bucket exists on emulator if emulator host is set
    ensure_emulator_storage_bucket()

    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Care Coordination API for urgent healthcare navigation. Not a diagnostic system.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permits local dev and preview ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}s"
    return response


# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {
        "service": settings.PROJECT_NAME,
        "status": "online",
        "notice": "DEMO / SIMULATED care coordination platform. Clinicians make 100% of medical assessments.",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "aiModel": settings.GEMINI_MODEL,
        "emulators": {
            "firestore": settings.FIRESTORE_EMULATOR_HOST,
            "auth": settings.FIREBASE_AUTH_EMULATOR_HOST,
            "storage": settings.FIREBASE_STORAGE_EMULATOR_HOST,
        },
    }

