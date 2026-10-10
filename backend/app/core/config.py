import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _BACKEND_DIR / ".env"

# Explicitly load .env file into os.environ before service or SDK initialization
if _ENV_FILE.exists():
    load_dotenv(dotenv_path=_ENV_FILE, override=False)
else:
    load_dotenv(dotenv_path=".env", override=False)


class Settings(BaseSettings):
    PROJECT_NAME: str = "MedBridge AI"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    
    # Gemini AI configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_TIMEOUT_SECONDS: int = 60
    
    # Firebase / Google Cloud configuration
    FIREBASE_PROJECT_ID: str = "demo-medbridge"
    FIRESTORE_EMULATOR_HOST: Optional[str] = "127.0.0.1:8080"
    FIREBASE_AUTH_EMULATOR_HOST: Optional[str] = "127.0.0.1:9099"
    FIREBASE_STORAGE_EMULATOR_HOST: Optional[str] = "127.0.0.1:9199"
    STORAGE_BUCKET_NAME: str = "medbridge-ai-documents"
    
    # Document Streaming / Download Token Signing Secret
    DOC_STREAM_SECRET: Optional[str] = None
    
    # CORS
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    
    model_config = SettingsConfigDict(
        env_file=(str(_ENV_FILE), ".env"),
        extra="ignore",
    )


settings = Settings()

# Synchronize emulator & project configuration to os.environ for Google Cloud and Firebase SDKs
if settings.FIRESTORE_EMULATOR_HOST and "FIRESTORE_EMULATOR_HOST" not in os.environ:
    os.environ["FIRESTORE_EMULATOR_HOST"] = settings.FIRESTORE_EMULATOR_HOST

if settings.FIREBASE_AUTH_EMULATOR_HOST and "FIREBASE_AUTH_EMULATOR_HOST" not in os.environ:
    os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = settings.FIREBASE_AUTH_EMULATOR_HOST

# Google Cloud Storage SDK explicitly requires STORAGE_EMULATOR_HOST with http:// scheme
storage_host = os.environ.get("STORAGE_EMULATOR_HOST") or settings.FIREBASE_STORAGE_EMULATOR_HOST
if storage_host:
    formatted_storage_host = f"http://{storage_host}" if not storage_host.startswith("http") else storage_host
    os.environ["STORAGE_EMULATOR_HOST"] = formatted_storage_host

# Google Cloud SDKs look for GCLOUD_PROJECT / GOOGLE_CLOUD_PROJECT
if settings.FIREBASE_PROJECT_ID:
    if "GCLOUD_PROJECT" not in os.environ:
        os.environ["GCLOUD_PROJECT"] = settings.FIREBASE_PROJECT_ID
    if "GOOGLE_CLOUD_PROJECT" not in os.environ:
        os.environ["GOOGLE_CLOUD_PROJECT"] = settings.FIREBASE_PROJECT_ID

if settings.DOC_STREAM_SECRET and "DOC_STREAM_SECRET" not in os.environ:
    os.environ["DOC_STREAM_SECRET"] = settings.DOC_STREAM_SECRET
