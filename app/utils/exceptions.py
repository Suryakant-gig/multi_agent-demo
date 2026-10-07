from typing import Optional, Dict, Any

class AppException(Exception):
    """Base application exception."""
    def __init__(self, message: str, status_code: int = 400, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class InvalidFileException(AppException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=400, details=details)


class FileTooLargeException(AppException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=message, status_code=413, details=details)


class SessionNotFoundException(AppException):
    def __init__(self, session_id: str):
        super().__init__(
            message=f"Session '{session_id}' not found.",
            status_code=404,
            details={"session_id": session_id}
        )


class FileNotFoundException(AppException):
    def __init__(self, file_id: str):
        super().__init__(
            message=f"File '{file_id}' not found in active session.",
            status_code=404,
            details={"file_id": file_id}
        )


class ToolExecutionException(AppException):
    def __init__(self, tool_name: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Tool '{tool_name}' failed: {message}",
            status_code=500,
            details=details or {"tool_name": tool_name}
        )


class ChartGenerationException(AppException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=f"Chart generation error: {message}", status_code=400, details=details)


class QueryUnderstandingException(AppException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message=f"Query error: {message}", status_code=400, details=details)
