import os
import shutil
import tempfile
import pytest
import pandas as pd
from fastapi.testclient import TestClient
from app.main import app
from app.state.session_manager import session_manager
from app.services.file_service import file_service
from app.services.storage_engine import storage_engine


@pytest.fixture(scope="session")
def test_client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    """Cleans in-memory sessions before each test."""
    session_manager._sessions.clear()
    yield
    session_manager._sessions.clear()


@pytest.fixture
def sample_csv_path(tmp_path):
    csv_file = tmp_path / "test_sales.csv"
    data = """product,category,revenue,quantity,region
Laptop Pro,Electronics,2500,2,North
Smartphone,Electronics,1200,3,South
Coffee Maker,Home,150,5,East
Desk Chair,Furniture,300,1,West
Monitor 4K,Electronics,800,2,North
Headphones,Audio,200,4,South
Blender,Home,100,2,East
Bookshelf,Furniture,250,1,West
"""
    csv_file.write_text(data, encoding="utf-8")
    return str(csv_file)


@pytest.fixture
def sample_excel_path(tmp_path):
    xlsx_file = tmp_path / "test_sales.xlsx"
    df = pd.DataFrame({
        "product": ["Tablet", "Smartwatch", "Keyboard"],
        "category": ["Electronics", "Wearables", "Accessories"],
        "revenue": [600, 400, 150],
        "quantity": [3, 2, 5]
    })
    df.to_excel(xlsx_file, index=False)
    return str(xlsx_file)


@pytest.fixture
def populated_session(sample_csv_path):
    session = session_manager.create_session("test-session-1")
    meta = file_service.process_and_store_file(
        file_path=sample_csv_path,
        original_filename="test_sales.csv",
        session_id=session.session_id
    )
    return session.session_id, meta
