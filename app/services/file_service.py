import os
import uuid
import shutil
from typing import Tuple, Optional, List, Union
from fastapi import UploadFile
import pandas as pd
import openpyxl
from app.utils.config import settings
from app.utils.logger import logger
from app.utils.exceptions import InvalidFileException, FileTooLargeException
from app.services.data_cleaner import DataCleaner
from app.services.schema_detector import SchemaDetector
from app.services.storage_engine import storage_engine
from app.models.domain import DatasetMetadata, DocumentMetadata, ColumnMetadata
from app.state.session_manager import session_manager
from app.documents.pdf_parser import pdf_parser
from app.documents.chunker import document_chunker
from app.documents.document_store import document_store


class FileService:
    """
    Handles file upload, validation, streaming ingestion for tabular data (CSV/Excel)
    and page-level text extraction and chunking for PDF documents.
    """

    ALLOWED_TABULAR_EXTENSIONS = {".csv", ".xlsx", ".xls"}
    ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".pdf"}

    def __init__(self, upload_dir: Optional[str] = None):
        self.upload_dir = upload_dir or settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)

    def validate_file(self, filename: str, content_size_bytes: int, allow_pdf: bool = False) -> str:
        """
        Validates filename, extension, and content size.
        allow_pdf defaults to False for strict backward compatibility with tabular-only validations.
        """
        if not filename:
            raise InvalidFileException("Filename is missing.")

        _, ext = os.path.splitext(filename.lower())
        allowed = self.ALLOWED_EXTENSIONS if allow_pdf else self.ALLOWED_TABULAR_EXTENSIONS
        if ext not in allowed:
            raise InvalidFileException(
                f"Unsupported file format '{ext}'. Allowed extensions are: {', '.join(sorted(allowed))}"
            )

        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if content_size_bytes > max_bytes:
            raise FileTooLargeException(
                f"File size exceeds the limit of {settings.MAX_UPLOAD_SIZE_MB}MB.",
                details={"size_bytes": content_size_bytes, "max_bytes": max_bytes}
            )

        if content_size_bytes == 0:
            raise InvalidFileException("Uploaded file is empty (0 bytes).")

        return ext

    async def save_upload_to_disk(self, upload_file: UploadFile) -> Tuple[str, int]:
        file_id = str(uuid.uuid4())
        safe_name = f"{file_id}_{upload_file.filename}"
        dest_path = os.path.join(self.upload_dir, safe_name)

        size_bytes = 0
        with open(dest_path, "wb") as buffer:
            while chunk := await upload_file.read(1024 * 1024):  # 1MB chunks
                size_bytes += len(chunk)
                buffer.write(chunk)

        return dest_path, size_bytes

    def process_and_store_file(
        self,
        file_path: str,
        original_filename: str,
        session_id: str
    ) -> Union[DatasetMetadata, DocumentMetadata]:
        file_size = os.path.getsize(file_path)
        ext = self.validate_file(original_filename, file_size, allow_pdf=True)

        # 1. PDF Document Pipeline
        if ext == ".pdf":
            return self._process_pdf_file(file_path, original_filename, file_size, session_id)

        # 2. Tabular Pipeline (CSV & Excel)
        file_id = str(uuid.uuid4())[:8]
        table_name = f"data_{file_id}"
        total_rows = 0
        detected_schema = []

        try:
            if ext == ".csv":
                total_rows, detected_schema = self._process_csv_file(file_path, session_id, table_name)
            elif ext in (".xlsx", ".xls"):
                total_rows, detected_schema = self._process_excel_file(file_path, session_id, table_name)

        except pd.errors.EmptyDataError:
            raise InvalidFileException("File is empty or contains no valid rows.")
        except InvalidFileException:
            raise
        except Exception as e:
            logger.error(f"Error processing tabular file: {e}", exc_info=True)
            raise InvalidFileException(f"Failed to parse and process file: {str(e)}")

        meta = DatasetMetadata(
            file_id=file_id,
            file_name=original_filename,
            file_size_bytes=file_size,
            row_count=total_rows,
            column_count=len(detected_schema),
            columns=detected_schema,
            db_table_name=table_name
        )

        session_manager.register_file(session_id=session_id, file_meta=meta, storage_path=file_path)
        return meta

    def _process_csv_file(self, file_path: str, session_id: str, table_name: str) -> Tuple[int, List[ColumnMetadata]]:
        chunksize = settings.CHUNK_SIZE_ROWS
        reader = pd.read_csv(file_path, chunksize=chunksize, low_memory=False)
        total_rows = 0
        detected_schema = []
        is_first_chunk = True

        for chunk in reader:
            if chunk.empty and is_first_chunk:
                raise InvalidFileException("CSV file contains no data rows.")

            cleaned_chunk, _ = DataCleaner.clean_dataframe(chunk)
            if is_first_chunk:
                detected_schema = SchemaDetector.detect_schema(cleaned_chunk)

            storage_engine.create_table_from_chunk(
                session_id=session_id,
                table_name=table_name,
                df_chunk=cleaned_chunk,
                is_first_chunk=is_first_chunk
            )
            total_rows += len(cleaned_chunk)
            is_first_chunk = False

        if total_rows == 0:
            raise InvalidFileException("CSV file contains no data rows.")

        return total_rows, detected_schema

    def _process_excel_file(self, file_path: str, session_id: str, table_name: str) -> Tuple[int, List[ColumnMetadata]]:
        """
        Streaming memory-efficient Excel ingestion.
        Uses openpyxl read_only iterator for .xlsx to avoid loading entire workbooks into RAM.
        Falls back to pd.read_excel for legacy formats (.xls).
        """
        _, ext = os.path.splitext(file_path.lower())

        if ext == ".xlsx":
            try:
                wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
                sheet = wb.active
                row_iterator = sheet.iter_rows(values_only=True)
                
                try:
                    headers = next(row_iterator, None)
                except StopIteration:
                    headers = None

                if not headers or all(h is None for h in headers):
                    wb.close()
                    raise InvalidFileException("Excel file contains no data rows.")

                clean_headers = [str(h).strip() if h is not None else f"col_{i}" for i, h in enumerate(headers)]
                chunk_rows = []
                total_rows = 0
                detected_schema = []
                is_first_chunk = True

                for row in row_iterator:
                    if all(cell is None for cell in row):
                        continue
                    padded_row = list(row[:len(clean_headers)])
                    if len(padded_row) < len(clean_headers):
                        padded_row.extend([None] * (len(clean_headers) - len(padded_row)))
                    chunk_rows.append(padded_row)

                    if len(chunk_rows) >= settings.CHUNK_SIZE_ROWS:
                        chunk_df = pd.DataFrame(chunk_rows, columns=clean_headers)
                        cleaned_chunk, _ = DataCleaner.clean_dataframe(chunk_df)
                        if is_first_chunk:
                            detected_schema = SchemaDetector.detect_schema(cleaned_chunk)
                        storage_engine.create_table_from_chunk(
                            session_id=session_id,
                            table_name=table_name,
                            df_chunk=cleaned_chunk,
                            is_first_chunk=is_first_chunk
                        )
                        total_rows += len(cleaned_chunk)
                        is_first_chunk = False
                        chunk_rows = []

                if chunk_rows:
                    chunk_df = pd.DataFrame(chunk_rows, columns=clean_headers)
                    cleaned_chunk, _ = DataCleaner.clean_dataframe(chunk_df)
                    if is_first_chunk:
                        detected_schema = SchemaDetector.detect_schema(cleaned_chunk)
                    storage_engine.create_table_from_chunk(
                        session_id=session_id,
                        table_name=table_name,
                        df_chunk=cleaned_chunk,
                        is_first_chunk=is_first_chunk
                    )
                    total_rows += len(cleaned_chunk)

                wb.close()
                if total_rows == 0:
                    raise InvalidFileException("Excel file contains no data rows.")
                return total_rows, detected_schema

            except InvalidFileException:
                raise
            except Exception as e:
                logger.warning(f"openpyxl streaming read failed, falling back to pd.read_excel: {e}")

        # Fallback for .xls or complex sheets
        df = pd.read_excel(file_path)
        if df.empty:
            raise InvalidFileException("Excel file contains no data rows.")

        cleaned_df, _ = DataCleaner.clean_dataframe(df)
        detected_schema = SchemaDetector.detect_schema(cleaned_df)
        storage_engine.create_table_from_chunk(
            session_id=session_id,
            table_name=table_name,
            df_chunk=cleaned_df,
            is_first_chunk=True
        )
        return len(cleaned_df), detected_schema

    def _process_pdf_file(
        self,
        file_path: str,
        original_filename: str,
        file_size: int,
        session_id: str
    ) -> DocumentMetadata:
        pages, is_scanned, total_chars = pdf_parser.extract_pages(file_path)
        doc_id = str(uuid.uuid4())[:8]
        page_count = len(pages)

        if is_scanned:
            chunks = []
            logger.info(f"PDF '{original_filename}' is scanned or image-based. Stored metadata without text chunks.")
        else:
            chunks = document_chunker.chunk_document(
                document_id=doc_id,
                file_name=original_filename,
                pages=pages
            )
            document_store.store_chunks(session_id=session_id, chunks=chunks)

        doc_meta = DocumentMetadata(
            document_id=doc_id,
            file_name=original_filename,
            file_size_bytes=file_size,
            page_count=page_count,
            chunk_count=len(chunks),
            is_scanned=is_scanned
        )

        session_manager.register_document(session_id=session_id, doc_meta=doc_meta, storage_path=file_path)
        return doc_meta


file_service = FileService()
