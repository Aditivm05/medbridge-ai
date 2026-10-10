from fastapi import APIRouter
from app.api.routers import health, auth, cases, documents, audit

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(cases.router)
api_router.include_router(documents.router)
api_router.include_router(audit.router)

