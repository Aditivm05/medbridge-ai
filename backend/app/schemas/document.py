from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_DOCUMENTS_PER_CASE = 5

ALLOWED_MIME_TYPES = {
    "application/pdf": [".pdf"],
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
}

MAGIC_BYTE_SIGNATURES = {
    "application/pdf": b"%PDF-",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}


def validate_magic_bytes(content: bytes, mime_type: str) -> bool:
    """Verifies that the initial bytes of content match the declared MIME type signature."""
    expected_magic = MAGIC_BYTE_SIGNATURES.get(mime_type)
    if not expected_magic:
        return False
    return content.startswith(expected_magic)


class ExtractionStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    EXTRACTED = "EXTRACTED"
    NEEDS_OCR = "NEEDS_OCR"
    FAILED = "FAILED"


class PageText(BaseModel):
    pageNumber: int
    text: str
    charCount: int
    status: ExtractionStatus = ExtractionStatus.EXTRACTED


class DocumentUploadIntentRequest(BaseModel):
    fileName: str = Field(..., min_length=1, max_length=255)
    mimeType: str
    sizeBytes: int = Field(..., gt=0, le=MAX_FILE_SIZE_BYTES)


class DocumentUploadIntentResponse(BaseModel):
    documentId: str
    caseId: str
    storagePath: str
    uploadUrl: str
    expiresInSeconds: int = 900  # 15 minutes


class DocumentResponse(BaseModel):
    documentId: str
    caseId: str
    patientId: str
    fileName: str
    storagePath: str
    mimeType: str
    sizeBytes: int
    magicBytesValidated: bool = True
    extractionStatus: ExtractionStatus = ExtractionStatus.PENDING
    pageCount: Optional[int] = None
    pages: list[PageText] = Field(default_factory=list)
    extractedText: Optional[str] = None
    ocrStatus: str = "pending"
    errorMessage: Optional[str] = None
    uploadedAt: datetime
    extractedAt: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentTextResponse(BaseModel):
    documentId: str
    caseId: str
    extractionStatus: ExtractionStatus
    pageCount: Optional[int] = None
    pages: list[PageText] = Field(default_factory=list)
    fullText: Optional[str] = None
    errorMessage: Optional[str] = None
    extractedAt: Optional[datetime] = None


class DocumentDownloadUrlResponse(BaseModel):
    documentId: str
    caseId: str
    fileName: str
    downloadUrl: str
    expiresInSeconds: int = 300
    isEmulatorFallback: bool = False

