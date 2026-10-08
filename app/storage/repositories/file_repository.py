import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.storage.models import UploadedFileModel, DatasetModel
from app.storage.database import get_session_factory
from app.models.domain import DatasetMetadata, ColumnMetadata
from app.utils.logger import logger


class FileRepository:
    """
    Repository for persisting uploaded file metadata and datasets in PostgreSQL.
    """

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def get_session(self) -> Session:
        return self._session_factory()

    def save_file_metadata(
        self,
        file_id: str,
        conv_id: str,
        file_name: str,
        file_type: str,
        file_size: int,
        storage_path: str
    ) -> UploadedFileModel:
        with self.get_session() as db:
            file_record = UploadedFileModel(
                id=file_id,
                conversation_id=conv_id,
                file_name=file_name,
                file_type=file_type,
                file_size=file_size,
                storage_path=storage_path,
                created_at=datetime.datetime.utcnow()
            )
            merged = db.merge(file_record)
            db.commit()
            return merged

    def save_dataset_metadata(self, dataset_meta: DatasetMetadata, conv_id: str, storage_path: str = "") -> None:
        with self.get_session() as db:
            # 1. Ensure file record exists
            file_rec = db.query(UploadedFileModel).filter(UploadedFileModel.id == dataset_meta.file_id).first()
            if not file_rec:
                file_rec = UploadedFileModel(
                    id=dataset_meta.file_id,
                    conversation_id=conv_id,
                    file_name=dataset_meta.file_name,
                    file_type="csv" if dataset_meta.file_name.lower().endswith(".csv") else "xlsx",
                    file_size=dataset_meta.file_size_bytes,
                    storage_path=storage_path,
                    created_at=dataset_meta.uploaded_at or datetime.datetime.utcnow()
                )
                db.merge(file_rec)
                db.flush()

            # 2. Dataset record
            ds_rec = DatasetModel(
                id=f"ds_{dataset_meta.file_id}",
                file_id=dataset_meta.file_id,
                table_name=dataset_meta.db_table_name,
                row_count=dataset_meta.row_count,
                column_count=dataset_meta.column_count,
                schema_metadata={"columns": [c.model_dump() for c in dataset_meta.columns]},
                created_at=dataset_meta.uploaded_at or datetime.datetime.utcnow()
            )
            db.merge(ds_rec)
            db.commit()
            logger.info(f"Persisted dataset {dataset_meta.file_name} to PostgreSQL for conversation {conv_id}")

    def get_datasets_for_conversation(self, conv_id: str) -> Dict[str, DatasetMetadata]:
        with self.get_session() as db:
            results = (
                db.query(DatasetModel, UploadedFileModel)
                .join(UploadedFileModel, DatasetModel.file_id == UploadedFileModel.id)
                .filter(UploadedFileModel.conversation_id == conv_id)
                .all()
            )
            datasets = {}
            for ds, f in results:
                raw_cols = (ds.schema_metadata or {}).get("columns", [])
                cols = [ColumnMetadata(**c) for c in raw_cols]
                meta = DatasetMetadata(
                    file_id=f.id,
                    file_name=f.file_name,
                    file_size_bytes=f.file_size or 0,
                    row_count=ds.row_count or 0,
                    column_count=ds.column_count or 0,
                    columns=cols,
                    db_table_name=ds.table_name,
                    uploaded_at=ds.created_at
                )
                datasets[f.id] = meta
            return datasets

    def get_files_for_conversation(self, conv_id: str) -> List[Dict[str, Any]]:
        with self.get_session() as db:
            files = db.query(UploadedFileModel).filter(UploadedFileModel.conversation_id == conv_id).all()
            return [
                {
                    "file_id": f.id,
                    "file_name": f.file_name,
                    "file_type": f.file_type,
                    "file_size": f.file_size,
                    "storage_path": f.storage_path,
                    "created_at": f.created_at.isoformat()
                }
                for f in files
            ]


file_repository = FileRepository()
