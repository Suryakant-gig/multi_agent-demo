import io
import os
import pytest
from pypdf import PdfWriter
from fastapi.testclient import TestClient
from app.documents.pdf_parser import pdf_parser
from app.documents.chunker import document_chunker
from app.documents.document_store import document_store
from app.retrieval.document_retriever import document_retriever
from app.state.session_manager import session_manager
from app.services.file_service import file_service


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Generates a multi-page PDF with extractable text for testing."""
    writer = PdfWriter()
    # Page 1
    writer.add_blank_page(width=300, height=300)
    # Page 2
    writer.add_blank_page(width=300, height=300)

    pdf_file = tmp_path / "research_paper.pdf"
    with open(pdf_file, "wb") as f:
        writer.write(f)

    # Let's write text to pages using PdfWriter metadata / stream or reportlab / pypdf
    return str(pdf_file)


def create_text_pdf(path: str, pages_text: list):
    """Creates a real text PDF using pypdf."""
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, create_string_object, DictionaryObject, ArrayObject, DecodedStreamObject

    writer = PdfWriter()
    for text in pages_text:
        page = writer.add_blank_page(width=400, height=400)
        # Add basic text content stream
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 350 Td ({text}) Tj ET".encode("latin-1", "replace"))
        page[NameObject("/Contents")] = stream

        font = DictionaryObject()
        font[NameObject("/Type")] = NameObject("/Font")
        font[NameObject("/Subtype")] = NameObject("/Type1")
        font[NameObject("/BaseFont")] = NameObject("/Helvetica")

        fonts = DictionaryObject()
        fonts[NameObject("/F1")] = font
        res = DictionaryObject()
        res[NameObject("/Font")] = fonts
        page[NameObject("/Resources")] = res

    with open(path, "wb") as f:
        writer.write(f)


def test_pdf_parsing_and_page_extraction(tmp_path):
    pdf_path = str(tmp_path / "test_doc.pdf")
    create_text_pdf(pdf_path, [
        "This is page one discussing hybrid retrieval algorithms.",
        "This is page two detailing empirical benchmark evaluations."
    ])

    pages, is_scanned, total_chars = pdf_parser.extract_pages(pdf_path)
    assert len(pages) == 2
    assert is_scanned is False
    assert pages[0]["page_number"] == 1
    assert "hybrid retrieval" in pages[0]["text"]
    assert pages[1]["page_number"] == 2
    assert "benchmark" in pages[1]["text"]


def test_scanned_pdf_detection(tmp_path):
    # Blank PDF with no text represents scanned image document
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    blank_pdf = str(tmp_path / "scanned_doc.pdf")
    with open(blank_pdf, "wb") as f:
        writer.write(f)

    pages, is_scanned, total_chars = pdf_parser.extract_pages(blank_pdf)
    assert is_scanned is True
    assert total_chars == 0


def test_pdf_chunking_and_retrieval(tmp_path):
    session_id = "sess_pdf_retrieval_test"
    session_manager.create_session(session_id=session_id)

    pages = [
        {"page_number": 1, "text": "Section 1 Introduction to Dense Sparse Representations in RAG architectures."},
        {"page_number": 2, "text": "Section 2 Methodology and benchmark results demonstrating 94 percent accuracy."}
    ]

    chunks = document_chunker.chunk_document(
        document_id="doc_123",
        file_name="hybrid_rag.pdf",
        pages=pages
    )
    assert len(chunks) == 2
    assert chunks[0].page_number == 1
    assert chunks[1].page_number == 2

    # Store in DocumentStore
    document_store.store_chunks(session_id=session_id, chunks=chunks)

    # 1. Semantic query
    results = document_retriever.search_documents(
        session_id=session_id,
        query="methodology benchmark accuracy",
        top_k=2
    )
    assert len(results) > 0
    top = results[0]
    assert top["chunk"].page_number == 2
    assert "Page 2" in top["citation"].source_description
    assert top["citation"].citation_type == "pdf"

    # 2. Specific page query
    page_results = document_retriever.search_documents(
        session_id=session_id,
        query="Summarize page 1",
        top_k=1
    )
    assert len(page_results) == 1
    assert page_results[0]["chunk"].page_number == 1
    assert "Page 1" in page_results[0]["citation"].source_description


def test_pdf_upload_api(test_client: TestClient, tmp_path):
    pdf_path = str(tmp_path / "uploaded_study.pdf")
    create_text_pdf(pdf_path, ["Analysis of deep neural network architectures in production."])

    with open(pdf_path, "rb") as f:
        res = test_client.post(
            "/api/v1/upload",
            files={"file": ("uploaded_study.pdf", f, "application/pdf")},
            data={"session_id": "api_pdf_session"}
        )

    assert res.status_code == 201
    data = res.json()
    assert data["file_type"] == "pdf"
    assert data["file_name"] == "uploaded_study.pdf"
    assert data["page_count"] == 1
    assert "successfully parsed" in data["message"]
