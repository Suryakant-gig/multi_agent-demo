import os
import pytest
from app.services.file_service import file_service
from app.services.data_cleaner import DataCleaner
from app.utils.exceptions import InvalidFileException, FileTooLargeException
import pandas as pd


def test_data_cleaner():
    df = pd.DataFrame({
        "  Product Name! ": [" Laptop ", " Mouse"],
        "Unit Price ($)": [1200, 25],
        "123_invalid": ["A", "B"]
    })
    cleaned, rename_map = DataCleaner.clean_dataframe(df)
    cols = list(cleaned.columns)
    assert "product_name" in cols
    assert "unit_price" in cols
    assert "col_123_invalid" in cols
    assert cleaned["product_name"].iloc[0] == "Laptop"


def test_file_validation_unsupported_extension():
    with pytest.raises(InvalidFileException) as exc:
        file_service.validate_file("document.pdf", 1024)
    assert "Unsupported file format" in str(exc.value)


def test_file_validation_empty_file():
    with pytest.raises(InvalidFileException) as exc:
        file_service.validate_file("empty.csv", 0)
    assert "empty" in str(exc.value).lower()


def test_file_validation_too_large():
    huge_bytes = 150 * 1024 * 1024  # 150MB > 100MB
    with pytest.raises(FileTooLargeException):
        file_service.validate_file("large.csv", huge_bytes)


def test_csv_processing(sample_csv_path):
    meta = file_service.process_and_store_file(
        file_path=sample_csv_path,
        original_filename="test_sales.csv",
        session_id="test-csv-sess"
    )
    assert meta.row_count == 8
    assert meta.column_count == 5
    col_names = [c.name for c in meta.columns]
    assert "product" in col_names
    assert "revenue" in col_names


def test_excel_processing(sample_excel_path):
    meta = file_service.process_and_store_file(
        file_path=sample_excel_path,
        original_filename="test_sales.xlsx",
        session_id="test-excel-sess"
    )
    assert meta.row_count == 3
    assert meta.column_count == 4
    col_names = [c.name for c in meta.columns]
    assert "product" in col_names
    assert "wearables" not in col_names  # value, not column
