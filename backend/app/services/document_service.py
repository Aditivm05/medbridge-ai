import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import pypdf

from app.core.config import settings
from app.core.firestore_client import get_firestore_client, get_storage_client
from app.models.firestore_models import document_to_firestore_dict, document_from_firestore_dict
from app.schemas.document import (
    DocumentResponse,
    DocumentTextResponse,
    ExtractionStatus,
    PageText,
)
from app.schemas.audit import AuditEventType
from app.services.audit_service import audit_service

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 30
MIN_PAGE_CHAR_THRESHOLD = 25
EXTRACTION_TIMEOUT_SECONDS = 8.0


class DocumentService:
    def __init__(self, db=None, storage=None):
        self._db = db
        self._storage = storage
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)
        self.timeout_seconds = EXTRACTION_TIMEOUT_SECONDS

    @property
    def db(self):
        if self._db is None:
            self._db = get_firestore_client()
        return self._db

    @property
    def storage(self):
        if self._storage is None:
            self._storage = get_storage_client()
        return self._storage

    # Backward compatibility adapter for legacy tests accessing service._documents
    @property
    def _documents(self):
        parent = self
        class _DocsAdapter:
            def __getitem__(self, doc_id: str):
                doc = parent.get_document(doc_id)
                if not doc:
                    raise KeyError(doc_id)
                return doc

            def __setitem__(self, doc_id: str, doc: DocumentResponse):
                parent.register_document(doc)

            def get(self, doc_id: str, default=None):
                doc = parent.get_document(doc_id)
                return doc if doc is not None else default

            def values(self):
                return parent.list_all_documents()

            def __contains__(self, doc_id: str):
                return parent.get_document(doc_id) is not None

        return _DocsAdapter()

    def register_document(self, doc: DocumentResponse, file_bytes: Optional[bytes] = None) -> None:
        """
        Persists document record in Firestore and writes file bytes to the Storage emulator bucket.
        Zero local disk copy is retained.
        """
        with self._lock:
            doc_dict = document_to_firestore_dict(doc)
            # 1. Persist to Firestore under subcollection /cases/{caseId}/documents/{docId}
            self.db.collection("cases").document(doc.caseId).collection("documents").document(doc.documentId).set(doc_dict)
            # 2. Persist to top-level index /documents/{docId} for fast O(1) direct retrieval
            self.db.collection("documents").document(doc.documentId).set(doc_dict)

            # 3. Stream bytes directly to Storage emulator bucket
            if file_bytes is not None:
                bucket = self.storage.bucket(settings.STORAGE_BUCKET_NAME)
                blob = bucket.blob(doc.storagePath)
                blob.upload_from_string(file_bytes, content_type=doc.mimeType)

    def get_document(self, document_id: str, case_id: Optional[str] = None) -> Optional[DocumentResponse]:
        """Retrieves a document from Firestore."""
        with self._lock:
            if case_id:
                snap = self.db.collection("cases").document(case_id).collection("documents").document(document_id).get()
                if snap.exists:
                    return document_from_firestore_dict(document_id, snap.to_dict())

            # Fallback to top-level index
            snap = self.db.collection("documents").document(document_id).get()
            if snap.exists:
                return document_from_firestore_dict(document_id, snap.to_dict())
            return None

    def list_case_documents(self, case_id: str) -> List[DocumentResponse]:
        """Lists all verified documents under /cases/{caseId}/documents from Firestore."""
        with self._lock:
            snaps = self.db.collection("cases").document(case_id).collection("documents").stream()
            docs = [document_from_firestore_dict(s.id, s.to_dict()) for s in snaps]
            return sorted(docs, key=lambda d: d.uploadedAt, reverse=True)

    def list_all_documents(self) -> List[DocumentResponse]:
        """Lists all registered documents across all cases."""
        with self._lock:
            snaps = self.db.collection("documents").stream()
            return [document_from_firestore_dict(s.id, s.to_dict()) for s in snaps]

    def extract_pdf_pages(
        self,
        file_bytes: bytes,
        max_pages: int = MAX_PDF_PAGES,
        min_char_threshold: int = MIN_PAGE_CHAR_THRESHOLD,
    ) -> Tuple[ExtractionStatus, Optional[int], List[PageText], Optional[str], Optional[str]]:
        """
        Parses text per page from text-based PDFs using pypdf.
        Gracefully handles:
        - Encrypted / password-protected PDFs (marks FAILED with readable error)
        - Corrupted / malformed PDFs (marks FAILED with readable error)
        - Very long PDFs exceeding max_pages limit (marks FAILED with readable error)
        - Pages with little or no text (< min_char_threshold) are marked NEEDS_OCR without guessing content.
        """
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))

            # 1. Check encryption
            if reader.is_encrypted:
                return (
                    ExtractionStatus.FAILED,
                    None,
                    [],
                    None,
                    "PDF is password-protected or encrypted. Please provide an unencrypted document.",
                )

            total_pages = len(reader.pages)

            # 2. Check empty PDF
            if total_pages == 0:
                return (
                    ExtractionStatus.FAILED,
                    0,
                    [],
                    None,
                    "PDF contains zero pages or no readable catalog structure.",
                )

            # 3. Check page limit guard (default 30 pages)
            if total_pages > max_pages:
                return (
                    ExtractionStatus.FAILED,
                    total_pages,
                    [],
                    None,
                    f"PDF exceeds maximum limit of {max_pages} pages (found {total_pages} pages).",
                )

            pages_result: List[PageText] = []
            extracted_text_parts: List[str] = []
            any_page_needs_ocr = False

            for idx, page in enumerate(reader.pages):
                page_num = idx + 1
                try:
                    raw_text = page.extract_text() or ""
                    cleaned_text = raw_text.strip()
                except Exception as page_err:
                    logger.warning(f"Error extracting page {page_num}: {page_err}")
                    cleaned_text = ""

                char_count = len(cleaned_text)

                # Page threshold check: little or no text -> mark NEEDS_OCR
                if char_count < min_char_threshold:
                    page_status = ExtractionStatus.NEEDS_OCR
                    any_page_needs_ocr = True
                    pages_result.append(
                        PageText(
                            pageNumber=page_num,
                            text=cleaned_text,
                            charCount=char_count,
                            status=page_status,
                        )
                    )
                else:
                    page_status = ExtractionStatus.EXTRACTED
                    pages_result.append(
                        PageText(
                            pageNumber=page_num,
                            text=cleaned_text,
                            charCount=char_count,
                            status=page_status,
                        )
                    )
                    extracted_text_parts.append(f"--- [Page {page_num}] ---\n{cleaned_text}")

            overall_status = ExtractionStatus.NEEDS_OCR if any_page_needs_ocr else ExtractionStatus.EXTRACTED
            full_text = "\n\n".join(extracted_text_parts) if extracted_text_parts else None

            return (overall_status, total_pages, pages_result, full_text, None)

        except Exception as e:
            logger.error(f"Failed to parse PDF bytes: {e}", exc_info=True)
            return (
                ExtractionStatus.FAILED,
                None,
                [],
                None,
                f"Corrupted or invalid PDF format: {str(e)}",
            )

    def process_document_extraction(
        self,
        document_id: str,
        file_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        case_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> DocumentResponse:
        """
        Executes text extraction with timeout protection, updates Firestore record,
        and logs audit trail events.
        Never crashes the server.
        """
        doc = self.get_document(document_id, case_id=case_id)
        if not doc:
            raise ValueError(f"Document '{document_id}' not found.")

        target_case_id = case_id or doc.caseId
        target_mime = mime_type or doc.mimeType

        # If file_bytes not provided in argument, stream directly from Storage emulator bucket
        if file_bytes is None:
            try:
                bucket = self.storage.bucket(settings.STORAGE_BUCKET_NAME)
                blob = bucket.blob(doc.storagePath)
                file_bytes = blob.download_as_bytes()
            except Exception as e:
                logger.error(f"Could not download blob '{doc.storagePath}' from Storage emulator: {e}")
                file_bytes = b""

        # Transition status to PROCESSING in Firestore
        processing_doc = doc.model_copy(update={"extractionStatus": ExtractionStatus.PROCESSING})
        with self._lock:
            doc_dict = document_to_firestore_dict(processing_doc)
            self.db.collection("cases").document(target_case_id).collection("documents").document(document_id).set(doc_dict)
            self.db.collection("documents").document(document_id).set(doc_dict)

        status = ExtractionStatus.PROCESSING
        page_count: Optional[int] = None
        pages: List[PageText] = []
        full_text: Optional[str] = None
        error_msg: Optional[str] = None

        if target_mime == "application/pdf":
            # Run PDF extraction with timeout protection
            try:
                future = self._executor.submit(self.extract_pdf_pages, file_bytes)
                status, page_count, pages, full_text, error_msg = future.result(
                    timeout=self.timeout_seconds
                )
            except FutureTimeoutError:
                status = ExtractionStatus.FAILED
                error_msg = f"PDF text extraction timed out after {self.timeout_seconds}s."
            except Exception as e:
                status = ExtractionStatus.FAILED
                error_msg = f"Unexpected extraction error: {str(e)}"
        elif target_mime.startswith("image/"):
            # Image files in Phase 6c have no text stream; mark NEEDS_OCR (Gemini OCR in 6e)
            status = ExtractionStatus.NEEDS_OCR
            page_count = 1
            pages = [
                PageText(
                    pageNumber=1,
                    text="",
                    charCount=0,
                    status=ExtractionStatus.NEEDS_OCR,
                )
            ]
            error_msg = "Image document has no embedded text stream; scheduled for visual OCR."
        else:
            status = ExtractionStatus.FAILED
            error_msg = f"Unsupported MIME type for text extraction: '{target_mime}'."

        now = datetime.utcnow()
        updated_doc = doc.model_copy(
            update={
                "extractionStatus": status,
                "pageCount": page_count,
                "pages": pages,
                "extractedText": full_text,
                "errorMessage": error_msg,
                "extractedAt": now,
                "ocrStatus": "needs_ocr" if status == ExtractionStatus.NEEDS_OCR else ("processed" if status == ExtractionStatus.EXTRACTED else "failed"),
            }
        )

        with self._lock:
            # Save final results to Firestore
            final_dict = document_to_firestore_dict(updated_doc)
            self.db.collection("cases").document(target_case_id).collection("documents").document(document_id).set(final_dict)
            self.db.collection("documents").document(document_id).set(final_dict)

        # Audit logging
        if status == ExtractionStatus.FAILED:
            audit_service.log_event(
                event_type=AuditEventType.DOC_EXTRACTION_FAILED,
                actor_id=actor_id or "system",
                actor_role=actor_role or "system",
                case_id=target_case_id,
                details={
                    "documentId": document_id,
                    "reason": error_msg,
                    "status": "failed",
                },
            )
        else:
            audit_service.log_event(
                event_type=AuditEventType.DOC_TEXT_EXTRACTED,
                actor_id=actor_id or "system",
                actor_role=actor_role or "system",
                case_id=target_case_id,
                details={
                    "documentId": document_id,
                    "pageCount": page_count,
                    "status": status.value,
                    "hasText": full_text is not None and len(full_text) > 0,
                },
            )

        return updated_doc


document_service = DocumentService()
