import uuid
import datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.storage.models import ToolCallModel
from app.storage.database import get_session_factory
from app.models.domain import ToolCallRecord
from app.utils.logger import logger


def sanitize_for_json(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(x) for x in obj]
    return obj


class ToolRepository:
    """
    Repository for persisting and querying tool execution audit logs in PostgreSQL.
    """

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session_factory()

    def get_session(self) -> Session:
        return self._session_factory()

    def record_tool_call(self, conv_id: str, tool_record: ToolCallRecord) -> str:
        with self.get_session() as db:
            tc_id = f"tc_{uuid.uuid4().hex[:12]}"

            # Store compact result metadata rather than huge binary blobs
            res = tool_record.result
            if isinstance(res, dict):
                res_meta = {
                    "keys": list(res.keys()),
                    "row_count": len(res.get("results", [])) if "results" in res else None,
                    "summary": str(res.get("summary", ""))[:500] if "summary" in res else None,
                }
            elif isinstance(res, list):
                res_meta = {"count": len(res)}
            else:
                res_meta = {"summary": str(res)[:500]}

            rec = ToolCallModel(
                id=tc_id,
                conversation_id=conv_id,
                tool_name=tool_record.tool_name,
                parameters=sanitize_for_json(tool_record.parameters),
                result_metadata=sanitize_for_json(res_meta),
                execution_time_ms=tool_record.execution_time_ms,
                success=tool_record.success,
                created_at=datetime.datetime.utcnow()
            )
            db.add(rec)
            db.commit()
            return tc_id

    def get_history(self, conv_id: str) -> List[Dict[str, Any]]:
        with self.get_session() as db:
            records = (
                db.query(ToolCallModel)
                .filter(ToolCallModel.conversation_id == conv_id)
                .order_by(ToolCallModel.created_at.asc())
                .all()
            )
            return [
                {
                    "id": r.id,
                    "tool_name": r.tool_name,
                    "parameters": r.parameters,
                    "result_metadata": r.result_metadata,
                    "execution_time_ms": r.execution_time_ms,
                    "success": r.success,
                    "created_at": r.created_at.isoformat()
                }
                for r in records
            ]


tool_repository = ToolRepository()
