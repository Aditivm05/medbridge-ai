from fastapi import APIRouter, HTTPException, UploadFile, File, Depends, BackgroundTasks, status, Response, Request
from typing import Optional, List
from datetime import datetime
import uuid
import os
import logging
from app.schemas.document import (
    DocumentUploadIntentRequest,
    DocumentUploadIntentResponse,
    DocumentResponse,
    DocumentTextResponse,
    DocumentDownloadUrlResponse,
    ExtractionStatus,
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    MAX_DOCUMENTS_PER_CASE,
    validate_magic_bytes,
)
from app.schemas.audit import AuditEventType
from app.core.state_machine import CaseStatus
from app.services.audit_service import audit_service
from app.services.case_service import case_service, CaseNotFoundError
from app.services.document_service import document_service
from app.core.auth import get_current_user, check_case_ownership, AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases/{case_id}/documents", tags=["documents"])

# In-memory document registry for local baseline testing
_documents_store = document_service._documents


@router.post("/upload-intent", response_model=DocumentUploadIntentResponse)
def request_upload_intent(
    case_id: str,
    req: DocumentUploadIntentRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Validates intent to upload a document against:
    - Case existence and ownership
    - Maximum 5 files per case limit
    - MIME type allowance
    - File extension matching MIME type
    - 10 MB maximum file size limit
    """
    try:
        case = case_service.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    check_case_ownership(case.patientId, current_user)

    # 1. Enforce 5 files per case limit
    if case.documentCount >= MAX_DOCUMENTS_PER_CASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum limit of {MAX_DOCUMENTS_PER_CASE} documents per case reached.",
        )

    # 2. Enforce 10 MB file size limit and positive size
    if req.sizeBytes <= 0 or req.sizeBytes > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size must be between 1 byte and {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB (10 MB limit).",
        )

    # 3. Enforce supported MIME type
    if req.mimeType not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"MIME type '{req.mimeType}' is not supported. Allowed: {list(ALLOWED_MIME_TYPES.keys())}.",
        )

    # 4. Enforce file extension matching MIME type
    ext = os.path.splitext(req.fileName)[1].lower()
    allowed_exts = ALLOWED_MIME_TYPES.get(req.mimeType, [])
    if not ext or ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' does not match MIME type '{req.mimeType}'. Allowed: {allowed_exts}.",
        )

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    storage_path = f"cases/{case_id}/{doc_id}_{req.fileName}"
    upload_url = f"/api/v1/cases/{case_id}/documents/{doc_id}/direct-upload"

    return DocumentUploadIntentResponse(
        documentId=doc_id,
        caseId=case_id,
        storagePath=storage_path,
        uploadUrl=upload_url,
        expiresInSeconds=900,
    )


@router.post("", response_model=DocumentResponse)
@router.post("/upload-and-verify", response_model=DocumentResponse)
async def upload_and_verify_document(
    case_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Validates uploaded file against:
    - Case existence and ownership
    - Maximum 5 files per case limit
    - File extension (allowed extensions: .pdf, .jpg, .jpeg, .png)
    - MIME type matching allowed types
    - Extension matching declared MIME type
    - 10 MB maximum file size limit (and non-empty 0 bytes check)
    - Binary magic bytes matching declared format signature (%PDF-, JPEG JFIF/EXIF, PNG)

    Non-blocking Phase 6c extraction:
    - Enqueues background task to extract per-page text or mark NEEDS_OCR
    - Never blocks the upload response
    """
    try:
        case = case_service.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    check_case_ownership(case.patientId, current_user)

    # 1. Enforce 5 files per case limit
    if case.documentCount >= MAX_DOCUMENTS_PER_CASE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum limit of {MAX_DOCUMENTS_PER_CASE} documents per case reached.",
        )

    filename = file.filename or ""

    # 2. Enforce file extension
    ext = os.path.splitext(filename)[1].lower()
    all_allowed_exts = [e for exts in ALLOWED_MIME_TYPES.values() for e in exts]
    if not ext or ext not in all_allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not permitted. Allowed: {all_allowed_exts}.",
        )

    # 3. Enforce declared MIME type
    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid MIME type '{mime_type}'. Supported: {list(ALLOWED_MIME_TYPES.keys())}.",
        )

    # Check extension matches declared MIME type
    allowed_exts_for_mime = ALLOWED_MIME_TYPES[mime_type]
    if ext not in allowed_exts_for_mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' does not match MIME type '{mime_type}'. Allowed: {allowed_exts_for_mime}.",
        )

    # 4. Read file bytes and enforce 10 MB limit & non-empty content
    chunk = await file.read(1024)
    file_bytes = chunk + await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file exceeds {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB limit.",
        )

    # 5. Magic byte binary verification
    if not validate_magic_bytes(file_bytes, mime_type):
        audit_service.log_event(
            event_type=AuditEventType.DOC_UPLOADED,
            actor_id=current_user.uid,
            actor_role=current_user.role,
            case_id=case_id,
            details={
                "status": "rejected",
                "reason": "Magic byte mismatch",
                "fileName": filename,
                "mimeType": mime_type,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not match the declared MIME type header (magic bytes check failed).",
        )

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    storage_path = f"cases/{case_id}/{doc_id}_{filename}"
    now = datetime.utcnow()

    doc_response = DocumentResponse(
        documentId=doc_id,
        caseId=case_id,
        patientId=case.patientId,
        fileName=filename,
        storagePath=storage_path,
        mimeType=mime_type,
        sizeBytes=len(file_bytes),
        magicBytesValidated=True,
        extractionStatus=ExtractionStatus.PROCESSING,
        pageCount=None,
        pages=[],
        extractedText=None,
        ocrStatus="pending",
        uploadedAt=now,
    )

    # Register document in service
    document_service.register_document(doc_response, file_bytes)

    # Atomically increment document count on case
    case_service.increment_document_count(case_id)

    audit_service.log_event(
        event_type=AuditEventType.DOC_UPLOADED,
        actor_id=current_user.uid,
        actor_role=current_user.role,
        case_id=case_id,
        details={"documentId": doc_id, "fileName": filename, "size": len(file_bytes)},
    )

    # Enqueue non-blocking text extraction task
    background_tasks.add_task(
        document_service.process_document_extraction,
        document_id=doc_id,
        file_bytes=file_bytes,
        mime_type=mime_type,
        case_id=case_id,
        actor_id=current_user.uid,
        actor_role=current_user.role,
    )

    return doc_response


@router.get("", response_model=List[DocumentResponse])
def list_case_documents(
    case_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Lists all verified documents attached to a specific case."""
    try:
        case = case_service.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    check_case_ownership(case.patientId, current_user)
    return document_service.list_case_documents(case_id)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_case_document(
    case_id: str,
    document_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Retrieves metadata of a specific document attached to a case."""
    try:
        case = case_service.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    check_case_ownership(case.patientId, current_user)
    doc = document_service.get_document(document_id)
    if not doc or doc.caseId != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for case '{case_id}'.",
        )
    return doc


@router.get("/{document_id}/text", response_model=DocumentTextResponse)
def get_document_extracted_text(
    case_id: str,
    document_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns per-page extracted text {pageNumber, text, charCount, status}
    for verifiable 'document + page' fact citations.
    Enforces strict patient ownership / clinician assignment gates.
    """
    try:
        case = case_service.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    check_case_ownership(case.patientId, current_user)

    doc = document_service.get_document(document_id)
    if not doc or doc.caseId != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for case '{case_id}'.",
        )

    return DocumentTextResponse(
        documentId=doc.documentId,
        caseId=doc.caseId,
        extractionStatus=doc.extractionStatus,
        pageCount=doc.pageCount,
        pages=doc.pages,
        fullText=doc.extractedText,
        errorMessage=doc.errorMessage,
        extractedAt=doc.extractedAt,
    )


@router.post("/{document_id}/extract", response_model=DocumentResponse)
def trigger_document_extraction(
    case_id: str,
    document_id: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Manually triggers / retries synchronous text extraction for a document.
    Enforces patient ownership / clinician assignment gates.
    """
    try:
        case = case_service.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    check_case_ownership(case.patientId, current_user)

    doc = document_service.get_document(document_id)
    if not doc or doc.caseId != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for case '{case_id}'.",
        )

    file_bytes = document_service._file_bytes_store.get(document_id)
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File binary content not cached for document '{document_id}'.",
        )

    return document_service.process_document_extraction(
        document_id=document_id,
        file_bytes=file_bytes,
        mime_type=doc.mimeType,
        case_id=case_id,
        actor_id=current_user.uid,
        actor_role=current_user.role,
    )


@router.get("/{document_id}/download-url", response_model=DocumentDownloadUrlResponse)
def get_document_download_url(
    case_id: str,
    document_id: str,
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Returns a short-lived download URL (5 minutes) after strict RBAC authorization:
    - Allowed:
      * Case patient owner (user.role == 'patient' and user.uid == case.patientId)
      * Verified assigned clinician when case status in {ACCEPTED, IN_CONSULTATION, COMPLETED}
      * Admin (user.role == 'admin')
    - Denied (HTTP 403 Forbidden with DOC_VIEW_DENIED audit log):
      * Other patients
      * Unassigned clinicians
      * Unverified clinicians
      * Assigned clinician on cases in any other status (e.g. CANCELLED, DRAFT, SUBMITTED, MATCHING, REASSIGNED)
    - Not Found (HTTP 404):
      * Case does not exist
      * Document does not exist or does not belong to case
    - Tokens are NEVER logged.
    """
    try:
        case = case_service.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    doc = document_service.get_document(document_id, case_id=case_id)
    if not doc or doc.caseId != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for case '{case_id}'.",
        )

    # Deliberate 403 vs 404 decision: resource exists, now enforce RBAC authorization
    is_authorized = False
    denial_reason = ""

    if current_user.role == "admin":
        is_authorized = True
    elif current_user.role == "patient":
        if current_user.uid == case.patientId:
            is_authorized = True
        else:
            denial_reason = "Patients can only access documents from their own cases."
    elif current_user.role == "clinician":
        if not current_user.is_verified_clinician:
            denial_reason = "Only verified clinicians may access clinical documents."
        elif case.assignedClinicianId != current_user.uid:
            denial_reason = "Clinician is not assigned to this case."
        elif case.status not in {CaseStatus.ACCEPTED, CaseStatus.IN_CONSULTATION, CaseStatus.COMPLETED}:
            denial_reason = f"Clinician document access not permitted when case status is '{case.status}' (requires ACCEPTED, IN_CONSULTATION, or COMPLETED)."
        else:
            is_authorized = True
    else:
        denial_reason = f"Role '{current_user.role}' is not authorized to access documents."

    if not is_authorized:
        audit_service.log_event(
            event_type=AuditEventType.DOC_VIEW_DENIED,
            actor_id=current_user.uid,
            actor_role=current_user.role,
            case_id=case_id,
            details={
                "documentId": document_id,
                "reason": denial_reason,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: {denial_reason}",
        )

    # Success: generate short-lived download URL (5 minutes)
    download_url, is_fallback, expires_in = document_service.generate_download_url(
        doc, user_id=current_user.uid
    )

    # Write DOC_VIEWED audit event (never log tokens or token-containing URLs)
    audit_service.log_event(
        event_type=AuditEventType.DOC_VIEWED,
        actor_id=current_user.uid,
        actor_role=current_user.role,
        case_id=case_id,
        details={
            "documentId": document_id,
            "fileName": doc.fileName,
            "mimeType": doc.mimeType,
            "isEmulatorFallback": is_fallback,
        },
    )

    return DocumentDownloadUrlResponse(
        documentId=doc.documentId,
        caseId=case_id,
        fileName=doc.fileName,
        downloadUrl=download_url,
        expiresInSeconds=expires_in,
        isEmulatorFallback=is_fallback,
    )


@router.get("/{document_id}/stream")
def stream_document_content(
    case_id: str,
    document_id: str,
    token: str,
    expires: int,
    userId: str,
):
    """
    Streams file bytes with signed token validation:
    - Binds caseId + documentId + userId + expiry using HMAC-SHA256
    - Uses constant-time hmac.compare_digest
    - Rejects expired or swapped tokens (HTTP 403)
    - If user is assigned clinician, enforces case status in {ACCEPTED, IN_CONSULTATION, COMPLETED}
    - Headers:
        X-Content-Type-Options: nosniff
        Cache-Control: no-store
        Content-Disposition: inline (for PDF) or attachment (for images)
    - Tokens are NEVER logged.
    """
    try:
        case = case_service.get_case(case_id)
    except CaseNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    doc = document_service.get_document(document_id, case_id=case_id)
    if not doc or doc.caseId != case_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found for case '{case_id}'.",
        )

    # 1. Verify stream token (binds caseId + documentId + userId + expiry)
    is_valid = document_service.verify_stream_token(
        case_id=case_id,
        document_id=document_id,
        user_id=userId,
        expiry=expires,
        token=token,
    )
    if not is_valid:
        audit_service.log_event(
            event_type=AuditEventType.DOC_VIEW_DENIED,
            actor_id=userId,
            actor_role="stream_bearer",
            case_id=case_id,
            details={
                "documentId": document_id,
                "reason": "Invalid, expired, or swapped stream token",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Invalid or expired download token.",
        )

    # 2. Clinician status guard: if userId is assigned clinician, ensure status is still permitted
    if userId == case.assignedClinicianId:
        if case.status not in {CaseStatus.ACCEPTED, CaseStatus.IN_CONSULTATION, CaseStatus.COMPLETED}:
            audit_service.log_event(
                event_type=AuditEventType.DOC_VIEW_DENIED,
                actor_id=userId,
                actor_role="clinician",
                case_id=case_id,
                details={
                    "documentId": document_id,
                    "reason": f"Case status '{case.status}' does not permit clinician document access.",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Case status '{case.status}' does not permit clinician document access.",
            )

    # 3. Retrieve document bytes from storage
    try:
        file_bytes = document_service.get_document_bytes(doc)
    except Exception as e:
        logger.error(f"Failed to retrieve document bytes for '{document_id}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve document content from storage.",
        )

    # 4. Content-Disposition: sanitize filename
    raw_filename = os.path.basename(doc.fileName or f"document_{doc.documentId}")
    safe_filename = "".join(c for c in raw_filename if c.isalnum() or c in "._- ")
    if not safe_filename.strip():
        safe_filename = f"document_{doc.documentId}"

    # Use inline only for PDFs, attachment for images
    if doc.mimeType == "application/pdf":
        disposition_type = "inline"
    else:
        disposition_type = "attachment"

    headers = {
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
        "Content-Disposition": f'{disposition_type}; filename="{safe_filename}"',
    }

    # Log view audit event on stream access (NEVER log the token)
    audit_service.log_event(
        event_type=AuditEventType.DOC_VIEWED,
        actor_id=userId,
        actor_role="stream_bearer",
        case_id=case_id,
        details={
            "documentId": document_id,
            "fileName": doc.fileName,
            "mimeType": doc.mimeType,
            "action": "streamed",
        },
    )

    return Response(
        content=file_bytes,
        media_type=doc.mimeType,
        headers=headers,
    )



