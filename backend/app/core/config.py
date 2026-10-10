from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    PROJECT_NAME: str = "MedBridge AI"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    PORT: int = 8000
    
    # Gemini AI configuration
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
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
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
