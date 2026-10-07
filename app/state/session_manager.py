import uuid
from typing import Dict, Optional, List, Any
import threading
from app.state.state_models import SessionState
from app.models.domain import DatasetMetadata, MessageRecord, ToolCallRecord, ChartPayload
from app.utils.exceptions import SessionNotFoundException, FileNotFoundException
from app.utils.logger import logger


class SessionManager:
    """
    In-memory thread-safe session manager with optional persistence capabilities.
    Maintains active files, schemas, chat histories, and cross-turn context.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SessionManager, cls).__new__(cls)
                cls._instance._sessions: Dict[str, SessionState] = {}
                cls._instance._sessions_lock = threading.Lock()
        return cls._instance

    def create_session(self, session_id: Optional[str] = None) -> SessionState:
        with self._sessions_lock:
            sid = session_id or str(uuid.uuid4())
            if sid not in self._sessions:
                state = SessionState(session_id=sid)
                self._sessions[sid] = state
                logger.info(f"Created new session: {sid}")
            return self._sessions[sid]

    def get_session(self, session_id: str) -> SessionState:
        with self._sessions_lock:
            if session_id not in self._sessions:
                raise SessionNotFoundException(session_id)
            return self._sessions[session_id]

    def get_or_create_session(self, session_id: Optional[str] = None) -> SessionState:
        if session_id and self.session_exists(session_id):
            return self.get_session(session_id)
        return self.create_session(session_id)

    def session_exists(self, session_id: str) -> bool:
        with self._sessions_lock:
            return session_id in self._sessions

    def register_file(self, session_id: str, file_meta: DatasetMetadata) -> None:
        with self._sessions_lock:
            session = self._sessions.get(session_id)
            if not session:
                session = SessionState(session_id=session_id)
                self._sessions[session_id] = session
            
            session.files[file_meta.file_id] = file_meta
            session.active_file_id = file_meta.file_id
            session.touch()
            logger.info(f"Registered file {file_meta.file_name} ({file_meta.file_id}) for session {session_id}")

    def get_active_file(self, session_id: str, file_id: Optional[str] = None) -> DatasetMetadata:
        session = self.get_session(session_id)
        target_file_id = file_id or session.active_file_id
        if not target_file_id or target_file_id not in session.files:
            raise FileNotFoundException(target_file_id or "NONE")
        return session.files[target_file_id]

    def append_message(self, session_id: str, message: MessageRecord) -> None:
        session = self.get_session(session_id)
        with self._sessions_lock:
            session.messages.append(message)
            session.touch()

    def update_context(
        self,
        session_id: str,
        query_result: Optional[Any] = None,
        query_summary: Optional[str] = None,
        tool_call: Optional[ToolCallRecord] = None,
        chart: Optional[ChartPayload] = None
    ) -> None:
        session = self.get_session(session_id)
        with self._sessions_lock:
            if query_result is not None:
                session.last_query_result = query_result
            if query_summary is not None:
                session.last_query_summary = query_summary
            if tool_call is not None:
                session.last_tool_call = tool_call
            if chart is not None:
                session.last_chart = chart
            session.touch()

    def clear_session(self, session_id: str) -> None:
        with self._sessions_lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.info(f"Cleared session {session_id}")


session_manager = SessionManager()
