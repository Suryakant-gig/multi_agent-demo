import pytest
from app.services.web_fetch_service import web_fetch_service
from app.tools.registry import tool_registry
from app.services.file_service import file_service
from app.utils.exceptions import AppException, ToolExecutionException, InvalidFileException


def test_ssrf_protection_blocks_loopback_and_metadata():
    # Loopback IP
    with pytest.raises(AppException) as exc1:
        web_fetch_service.validate_url("http://127.0.0.1:8000/admin")
    assert exc1.value.status_code == 403

    # Localhost string
    with pytest.raises(AppException) as exc2:
        web_fetch_service.validate_url("http://localhost:3000/api")
    assert exc2.value.status_code == 403

    # Cloud link-local metadata IP
    with pytest.raises(AppException) as exc3:
        web_fetch_service.validate_url("http://169.254.169.254/computeMetadata/v1/")
    assert exc3.value.status_code == 403


def test_disallowed_schemes_blocked():
    with pytest.raises(AppException) as exc:
        web_fetch_service.validate_url("file:///C:/Windows/System32/drivers/etc/hosts")
    assert exc.value.status_code == 400
    assert "Disallowed URL scheme" in str(exc.value)

    with pytest.raises(AppException):
        web_fetch_service.validate_url("ftp://example.com/file.txt")


def test_sql_read_only_enforcement(populated_session):
    session_id, _ = populated_session

    # Attempting DROP TABLE
    with pytest.raises(ToolExecutionException) as exc:
        tool_registry.execute_tool(
            "query_sql",
            session_id=session_id,
            sql_query="DROP TABLE data_sample;"
        )
    assert "read-only" in str(exc.value).lower() or "only select" in str(exc.value).lower() or "invalid" in str(exc.value).lower()

    # Attempting INSERT
    with pytest.raises(ToolExecutionException):
        tool_registry.execute_tool(
            "query_sql",
            session_id=session_id,
            sql_query="INSERT INTO data_sample VALUES (1, 'hack');"
        )


def test_unsupported_file_extension():
    with pytest.raises(InvalidFileException) as exc:
        file_service.validate_file("malicious.exe", 1024, allow_pdf=True)
    assert "Unsupported file format" in str(exc.value)

    with pytest.raises(InvalidFileException) as exc:
        file_service.validate_file("script.py", 1024, allow_pdf=True)
    assert "Unsupported file format" in str(exc.value)
