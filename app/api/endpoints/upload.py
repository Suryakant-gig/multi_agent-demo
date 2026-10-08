from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, status, HTTPException
from app.schemas.upload import UploadResponse
from app.schemas.common import ErrorResponse
from app.services.file_service import file_service
from app.state.session_manager import session_manager
from app.utils.exceptions import InvalidFileException, FileTooLargeException
from app.utils.logger import logger

router = APIRouter()


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload Excel, CSV, or PDF file",
    description="Accepts CSV, Excel (.xlsx, .xls), or PDF files, validates content, and indexes for analysis or retrieval.",
    responses={
        201: {"model": UploadResponse, "description": "File successfully parsed and ingested."},
        400: {"model": ErrorResponse, "description": "Invalid file format, empty file, or parsing error."},
        413: {"model": ErrorResponse, "description": "File size exceeds maximum upload limit."}
    },
    tags=["Files"]
)
async def upload_file(
    file: UploadFile = File(..., description="CSV, Excel, or PDF file to upload"),
    session_id: Optional[str] = Form(None, description="Optional existing session ID."),
    conversation_id: Optional[str] = Form(None, description="Optional existing conversation ID.")
):
    try:
        target_id = conversation_id or session_id
        session = session_manager.get_or_create_session(target_id)
        
        # Save upload to disk in chunks
        saved_path, size_bytes = await file_service.save_upload_to_disk(file)
        
        # Process and ingest
        meta = file_service.process_and_store_file(
            file_path=saved_path,
            original_filename=file.filename or "unknown",
            session_id=session.session_id
        )

        from app.models.domain import DocumentMetadata
        if isinstance(meta, DocumentMetadata):
            msg = (
                "This PDF appears to be scanned and requires OCR."
                if meta.is_scanned
                else f"PDF document '{meta.file_name}' successfully parsed and indexed ({meta.page_count} pages, {meta.chunk_count} chunks)."
            )
            return UploadResponse(
                session_id=session.session_id,
                conversation_id=session.conversation_id,
                file_id=meta.document_id,
                file_name=meta.file_name,
                file_size_bytes=meta.file_size_bytes,
                row_count=0,
                column_count=0,
                columns=[],
                file_type="pdf",
                page_count=meta.page_count,
                message=msg
            )

        return UploadResponse(
            session_id=session.session_id,
            conversation_id=session.conversation_id,
            file_id=meta.file_id,
            file_name=meta.file_name,
            file_size_bytes=meta.file_size_bytes,
            row_count=meta.row_count,
            column_count=meta.column_count,
            columns=meta.columns,
            file_type="tabular",
            message="File successfully parsed and indexed."
        )

    except (InvalidFileException, FileTooLargeException) as e:
        logger.warning(f"File upload validation failure: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Unexpected upload error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error processing file: {str(e)}")


@router.post(
    "/upload-sample",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Load included sample dataset",
    description="Loads prepackaged sample_sales.csv into session for immediate testing.",
    tags=["Files"]
)
def load_sample_file(session_id: Optional[str] = None):
    sample_path = "./data/sample_sales.csv"
    session = session_manager.get_or_create_session(session_id)
    meta = file_service.process_and_store_file(
        file_path=sample_path,
        original_filename="sample_sales.csv",
        session_id=session.session_id
    )

    return UploadResponse(
        session_id=session.session_id,
        file_id=meta.file_id,
        file_name=meta.file_name,
        file_size_bytes=meta.file_size_bytes,
        row_count=meta.row_count,
        column_count=meta.column_count,
        columns=meta.columns,
        message="Sample dataset loaded successfully."
    )

