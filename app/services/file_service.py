import os
import uuid
import shutil
from typing import Tuple, Optional
from fastapi import UploadFile
import pandas as pd
from app.utils.config import settings
from app.utils.logger import logger
from app.utils.exceptions import InvalidFileException, FileTooLargeException
from app.services.data_cleaner import DataCleaner
from app.services.schema_detector import SchemaDetector
from app.services.storage_engine import storage_engine
from app.models.domain import DatasetMetadata
from app.state.session_manager import session_manager


class FileService:
    """
    Handles file upload, validation, streaming ingestion,
    schema extraction, and storage engine registration.
    """

    ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

    def __init__(self, upload_dir: Optional[str] = None):
        self.upload_dir = upload_dir or settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)

    def validate_file(self, filename: str, content_size_bytes: int) -> str:
        if not filename:
            raise InvalidFileException("Filename is missing.")

        _, ext = os.path.splitext(filename.lower())
        if ext not in self.ALLOWED_EXTENSIONS:
            raise InvalidFileException(
                f"Unsupported file format '{ext}'. Allowed extensions are: {', '.join(self.ALLOWED_EXTENSIONS)}"
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

    def process_and_store_file(self, file_path: str, original_filename: str, session_id: str) -> DatasetMetadata:
        file_size = os.path.getsize(file_path)
        ext = self.validate_file(original_filename, file_size)
        file_id = str(uuid.uuid4())[:8]
        table_name = f"data_{file_id}"

        total_rows = 0
        detected_schema = []
        is_first_chunk = True

        try:
            if ext == ".csv":
                chunksize = settings.CHUNK_SIZE_ROWS
                # Process in chunks to prevent large memory spikes
                reader = pd.read_csv(file_path, chunksize=chunksize, low_memory=False)
                
                # Check if file has rows
                first = True
                for chunk in reader:
                    if chunk.empty and first:
                        raise InvalidFileException("CSV file contains no data rows.")
                    
                    cleaned_chunk, _ = DataCleaner.clean_dataframe(chunk)
                    if first:
                        detected_schema = SchemaDetector.detect_schema(cleaned_chunk)
                        first = False

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

            elif ext in (".xlsx", ".xls"):
                # Excel reading via pandas openpyxl
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
                total_rows = len(cleaned_df)

        except pd.errors.EmptyDataError:
            raise InvalidFileException("File is empty or contains no valid rows.")
        except InvalidFileException:
            raise
        except Exception as e:
            logger.error(f"Error processing tabular file: {e}")
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

        # Register with session manager
        session_manager.register_file(session_id=session_id, file_meta=meta)
        return meta


file_service = FileService()
