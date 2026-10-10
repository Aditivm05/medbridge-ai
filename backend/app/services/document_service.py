import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pypdf

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
    def __init__(self):
        self._documents: Dict[str, DocumentResponse] = {}
        self._file_bytes_store: Dict[str, bytes] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4)

    def register_document(self, doc: DocumentResponse, file_bytes: Optional[bytes] = None) -> None:
        """Stores document record and initial raw bytes in memory."""
        with self._lock:
            self._documents[doc.documentId] = doc
            if file_bytes is not None:
                self._file_bytes_store[doc.documentId] = file_bytes

    def get_document(self, document_id: str) -> Optional[DocumentResponse]:
        with self._lock:
            return self._documents.get(document_id)

    def list_case_documents(self, case_id: str) -> List[DocumentResponse]:
        with self._lock:
            return [d for d in self._documents.values() if d.caseId == case_id]

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
        file_bytes: bytes,
        mime_type: str,
        case_id: str,
        actor_id: str,
        actor_role: str,
    ) -> DocumentResponse:
        """
        Executes text extraction with timeout protection, updates the document record,
        and logs audit trail events.
        Never crashes the server.
        """
        doc = self.get_document(document_id)
        if not doc:
            raise ValueError(f"Document '{document_id}' not found.")

        # Transition status to PROCESSING
        with self._lock:
            self._documents[document_id] = doc.model_copy(
                update={"extractionStatus": ExtractionStatus.PROCESSING}
            )

        status = ExtractionStatus.PROCESSING
        page_count: Optional[int] = None
        pages: List[PageText] = []
        full_text: Optional[str] = None
        error_msg: Optional[str] = None

        if mime_type == "application/pdf":
            # Run PDF extraction with timeout protection
            try:
                future = self._executor.submit(self.extract_pdf_pages, file_bytes)
                status, page_count, pages, full_text, error_msg = future.result(
                    timeout=EXTRACTION_TIMEOUT_SECONDS
                )
            except FutureTimeoutError:
                status = ExtractionStatus.FAILED
                error_msg = f"PDF text extraction timed out after {EXTRACTION_TIMEOUT_SECONDS}s."
            except Exception as e:
                status = ExtractionStatus.FAILED
                error_msg = f"Unexpected extraction error: {str(e)}"
        elif mime_type.startswith("image/"):
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
            error_msg = f"Unsupported MIME type for text extraction: '{mime_type}'."

        now = datetime.utcnow()
        with self._lock:
            updated_doc = self._documents[document_id].model_copy(
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
            self._documents[document_id] = updated_doc

        # Emit append-only Audit Events
        if status in (ExtractionStatus.EXTRACTED, ExtractionStatus.NEEDS_OCR):
            audit_service.log_event(
                event_type=AuditEventType.DOC_TEXT_EXTRACTED,
                actor_id=actor_id,
                actor_role=actor_role,
                case_id=case_id,
                details={
                    "documentId": document_id,
                    "status": status.value,
                    "pageCount": page_count,
                    "pagesExtracted": len([p for p in pages if p.status == ExtractionStatus.EXTRACTED]),
                    "pagesNeedingOcr": len([p for p in pages if p.status == ExtractionStatus.NEEDS_OCR]),
                },
            )
        else:
            audit_service.log_event(
                event_type=AuditEventType.DOC_EXTRACTION_FAILED,
                actor_id=actor_id,
                actor_role=actor_role,
                case_id=case_id,
                details={
                    "documentId": document_id,
                    "status": status.value,
                    "reason": error_msg,
                },
            )

        return updated_doc


document_service = DocumentService()
