from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check():
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
