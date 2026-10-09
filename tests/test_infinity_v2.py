import os
import pytest
import pandas as pd
from app.state.session_manager import session_manager
from app.services.file_service import file_service
from app.agents.orchestrator import agent_orchestrator
from app.models.domain import IntentType
from app.documents.chunker import document_chunker
from app.documents.document_store import document_store
from app.tools.search_tool import SearchDataTool
from app.retrieval.document_retriever import document_retriever


@pytest.fixture
def multi_file_session(tmp_path):
    """Sets up a session with both a sales CSV and a DSA questions PDF."""
    session_id = "test_sess_infinity_v2"
    session_manager.create_session(session_id)

    # 1. Create and ingest Sales CSV (15 rows)
    csv_file = tmp_path / "sales.csv"
    csv_content = """Product,Region,Revenue,Quantity
Laptop Pro,North,2500,5
Smartphone,South,1200,8
Coffee Maker,East,150,12
Desk Chair,West,300,4
Monitor 4K,North,800,6
Headphones,South,200,15
Blender,East,100,7
Bookshelf,West,250,3
Keyboard,North,120,20
Mouse,South,60,30
Tablet,East,600,10
Smartwatch,West,400,9
Webcam,North,90,14
Speakers,South,180,11
Microwave,East,220,5
"""
    csv_file.write_text(csv_content, encoding="utf-8")
    dataset_meta = file_service.process_and_store_file(
        file_path=str(csv_file),
        original_filename="sales.csv",
        session_id=session_id
    )

    # 2. Ingest DSA PDF with 10 questions (Questions 21 to 30) across 2 pages
    pages = [
        {
            "page_number": 1,
            "text": """DSA Practice Sheet: Additional Questions
Question 21: Remove Duplicates from Sorted Array. Pattern: Two Pointers. Description: Given an integer array nums sorted in non-decreasing order, remove duplicates in-place.
Question 22: Best Time to Buy and Sell Stock. Pattern: Greedy / Dynamic Programming. Description: Maximize profit by choosing a single day to buy and a different day in the future to sell.
Question 23: Contains Duplicate. Pattern: Hash Set. Description: Given an integer array nums, return true if any value appears at least twice in the array.
Question 24: Product of Array Except Self. Pattern: Prefix Sum. Description: Given an integer array nums, return an array answer such that answer[i] is equal to product of all elements except nums[i].
Question 25: Maximum Subarray. Pattern: Kadane's Algorithm. Description: Find the subarray with the largest sum and return its sum."""
        },
        {
            "page_number": 2,
            "text": """Question 26: Maximum Product Subarray. Pattern: Dynamic Programming. Description: Find a contiguous non-empty subarray within an array that has the largest product.
Question 27: Find Minimum in Rotated Sorted Array. Pattern: Binary Search. Description: Given a sorted rotated array of unique elements, return the minimum element in O(log n).
Question 28: Search in Rotated Sorted Array. Pattern: Binary Search. Description: Given a sorted rotated array, search for target value in O(log n) runtime complexity.
Question 29: 3Sum. Pattern: Two Pointers. Description: Given an integer array nums, return all the triplets [nums[i], nums[j], nums[k]] such that they sum to 0.
Question 30: Container With Most Water. Pattern: Two Pointers. Description: Find two lines that together with the x-axis form a container, such that the container contains the most water."""
        }
    ]
    chunks = document_chunker.chunk_document(
        document_id="doc_dsa_pdf",
        file_name="DSA_Additional_Questions_21_30.pdf",
        pages=pages
    )
    document_store.store_chunks(session_id=session_id, chunks=chunks)

    # Ingest a secondary PDF to test multi-file disambiguation
    sec_pages = [
        {"page_number": 1, "text": "Annual Report 2025: Corporate financial results and quarterly earnings."}
    ]
    sec_chunks = document_chunker.chunk_document(
        document_id="doc_annual_report",
        file_name="annual_report.pdf",
        pages=sec_pages
    )
    document_store.store_chunks(session_id=session_id, chunks=sec_chunks)
    session = session_manager.get_session(session_id)
    session.active_document_id = "doc_dsa_pdf"

    return session_id, dataset_meta, "doc_dsa_pdf"


# ============================================================
# DATA TESTS (1-7)
# ============================================================

def test_data_first_5_rows(multi_file_session):
    """Test 1: First 5 rows must return source order rows 1-5."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Give me the first 5 rows from the Excel file.")

    assert res["table"] is not None
    table = res["table"]
    assert table["row_count"] == 5
    assert len(table["rows"]) == 5
    # Must be first 5 in source order
    assert table["rows"][0][0] == "Laptop Pro"
    assert table["rows"][1][0] == "Smartphone"
    assert table["rows"][2][0] == "Coffee Maker"
    assert table["rows"][3][0] == "Desk Chair"
    assert table["rows"][4][0] == "Monitor 4K"
    assert "|" in res["answer"]  # Markdown table present


def test_data_first_10_rows(multi_file_session):
    """Test 2: First 10 rows."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Give me the first 10 rows")

    assert res["table"] is not None
    assert res["table"]["row_count"] == 10
    assert len(res["table"]["rows"]) == 10
    assert res["table"]["rows"][0][0] == "Laptop Pro"
    assert res["table"]["rows"][9][0] == "Mouse"


def test_data_top_5_by_revenue(multi_file_session):
    """Test 3: Top 5 by revenue descending."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Give me the top 5 products by revenue.")

    assert res["table"] is not None
    table = res["table"]
    assert table["row_count"] == 5
    # Verify descending ordering
    rev_idx = table["columns"].index("Revenue") if "Revenue" in table["columns"] else (
        table["columns"].index("metric") if "metric" in table["columns"] else 1
    )
    revenues = [float(str(row[rev_idx]).replace(",", "")) for row in table["rows"]]
    assert revenues == sorted(revenues, reverse=True)
    assert revenues[0] == 2500.0  # Laptop Pro


def test_data_filter_records(multi_file_session):
    """Test 4: Filter records by region."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Give me all records where region is East")

    assert res["table"] is not None
    for row in res["table"]["rows"]:
        assert "East" in [str(val) for val in row]


def test_data_table_rendering(multi_file_session):
    """Test 5: Structured table payload and Markdown table rendering."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Show the first 3 rows")

    assert res["table"] is not None
    table = res["table"]
    assert "columns" in table
    assert "rows" in table
    assert "row_count" in table
    assert table["row_count"] == 3
    # Check Markdown formatting
    assert "| Product |" in res["answer"] or "| product |" in res["answer"]
    assert "|---" in res["answer"]


def test_data_aggregation(multi_file_session):
    """Test 6: Aggregation query."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "calculate average revenue by region")

    assert res["intent"] == IntentType.DATA_ANALYSIS.value
    assert len(res["citations"]) > 0


def test_data_sorting_direct_tool(multi_file_session):
    """Test 7: Direct tool deterministic sorting and first_n."""
    session_id, _, _ = multi_file_session
    tool = SearchDataTool()
    out = tool.execute(session_id=session_id, operation="top_n", sort_column="Revenue", n=3, ascending=True)

    assert out["table"] is not None
    rows = out["table"]["rows"]
    assert len(rows) == 3
    # Lowest revenue first: Mouse (60), Webcam (90), Blender (100)
    assert float(rows[0][2]) <= float(rows[1][2]) <= float(rows[2][2])


# ============================================================
# PDF TESTS (8-15)
# ============================================================

def test_pdf_first_5_questions(multi_file_session):
    """Test 8: First 5 questions in document order."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Give me the first 5 questions from the DSA PDF.")

    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert res["table"] is not None
    assert res["table"]["row_count"] == 5
    # Must preserve questions 21 to 25
    assert "21" in str(res["table"]["rows"][0][0])
    assert "25" in str(res["table"]["rows"][4][0])
    assert len(res["citations"]) > 0


def test_pdf_all_10_questions(multi_file_session):
    """Test 9: All 10 questions complete extraction."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Give me all 10 DSA questions.")

    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert res["table"] is not None
    assert res["table"]["row_count"] == 10
    assert len(res["table"]["rows"]) == 10
    # Questions 21 through 30
    assert "21" in str(res["table"]["rows"][0][0])
    assert "30" in str(res["table"]["rows"][9][0])


def test_pdf_questions_21_to_30(multi_file_session):
    """Test 10: Questions 21 to 30 range extraction."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Give me questions 21 to 30.")

    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert res["table"] is not None
    assert res["table"]["row_count"] == 10
    assert "21" in str(res["table"]["rows"][0][0])
    assert "30" in str(res["table"]["rows"][9][0])


def test_pdf_next_5_questions(multi_file_session):
    """Test 11: Turn 1 first 5, Turn 2 next 5."""
    session_id, _, _ = multi_file_session
    # Turn 1
    res1 = agent_orchestrator.process_query(session_id, "Give me the first 5 questions from the DSA PDF.")
    assert res1["table"]["row_count"] == 5
    assert "21" in str(res1["table"]["rows"][0][0])

    # Turn 2
    res2 = agent_orchestrator.process_query(session_id, "Now give me the next 5.")
    assert res2["table"] is not None
    assert res2["table"]["row_count"] == 5
    # Should start from question 26
    assert "26" in str(res2["table"]["rows"][0][0])
    assert "30" in str(res2["table"]["rows"][4][0])


def test_pdf_question_from_specific_page(multi_file_session):
    """Test 12: Question from a specific page."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "What is written on page 2 of the DSA PDF?")

    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert any(c.get("page_number") == 2 for c in res["citations"])
    assert "30" in res["answer"] or "Container" in res["answer"] or "26" in res["answer"]


def test_pdf_long_multi_chunk_expansion(multi_file_session):
    """Test 13: Stitches adjacent chunks seamlessly."""
    session_id, _, _ = multi_file_session
    chunks = document_store.get_chunks(session_id, "doc_dsa_pdf")
    stitched = document_retriever.stitch_chunks(chunks)
    assert "Question 21" in stitched
    assert "Question 30" in stitched


def test_pdf_duplicate_overlapping_chunks(multi_file_session):
    """Test 14: Deduplication removes redundant overlapping chunk text."""
    session_id, _, _ = multi_file_session
    # Overlapping chunks
    c1_text = "This is introductory text on algorithms and data structures."
    c2_text = "algorithms and data structures. Next topic is binary trees."
    from app.models.domain import DocumentChunk
    chunk_a = DocumentChunk(chunk_id="c1", document_id="d1", file_name="test.pdf", page_number=1, text=c1_text, chunk_index=0, document_order=0)
    chunk_b = DocumentChunk(chunk_id="c2", document_id="d1", file_name="test.pdf", page_number=1, text=c2_text, chunk_index=1, document_order=1)
    stitched = document_retriever.stitch_chunks([chunk_a, chunk_b])
    # The overlapping phrase should not be repeated twice consecutively
    assert stitched.count("algorithms and data structures. Next") == 1


def test_pdf_page_citation(multi_file_session):
    """Test 15: Page citations travel with retrieved data."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "What does the DSA PDF say about binary search?")

    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert len(res["citations"]) > 0
    pdf_citations = [c for c in res["citations"] if c.get("citation_type") == "pdf"]
    assert len(pdf_citations) > 0
    assert pdf_citations[0]["page_number"] in (1, 2)
    assert "DSA_Additional_Questions_21_30.pdf" in pdf_citations[0]["file_name"]


# ============================================================
# ROUTING TESTS (16-20)
# ============================================================

def test_routing_pdf_question(multi_file_session):
    """Test 16: PDF question routes strictly to document_search, no web search."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "What does the DSA PDF say about binary search?")

    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    # No web sources
    assert not any(s.get("source_type") == "web" for s in res.get("sources", []))


def test_routing_excel_question(multi_file_session):
    """Test 17: Excel question routes strictly to data tool."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Give me the first 5 rows from the Excel file.")

    assert res["intent"] in (IntentType.SEARCH_RETRIEVAL.value, "data_extraction")
    assert not any(s.get("source_type") == "web" for s in res.get("sources", []))


def test_routing_research_question(multi_file_session):
    """Test 18: Research question routes to Research Agent / web_search."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Find 5 recent research papers about binary search optimization.")

    assert res["intent"] == IntentType.RESEARCH.value
    assert len(res.get("sources", [])) > 0


def test_routing_pdf_plus_research(multi_file_session):
    """Test 19: PDF + Research routes to mixed hybrid orchestration."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Read the DSA PDF and find recent research papers about the concepts in it.")

    assert res["intent"] == IntentType.HYBRID.value
    has_pdf_cit = any(c.get("citation_type") == "pdf" for c in res["citations"])
    has_web_cit = any(c.get("citation_type") == "web" for c in res["citations"])
    assert has_pdf_cit is True
    assert has_web_cit is True


def test_routing_excel_plus_research(multi_file_session):
    """Test 20: Excel + Research routes to mixed hybrid orchestration."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "Analyze my sales Excel file and find research explaining why revenue changed.")

    assert res["intent"] == IntentType.HYBRID.value
    has_data_cit = any(c.get("citation_type") == "dataset" for c in res["citations"])
    has_web_cit = any(c.get("citation_type") == "web" for c in res["citations"])
    assert has_data_cit is True
    assert has_web_cit is True


# ============================================================
# CONVERSATION TESTS (21-25)
# ============================================================

def test_conversation_first_5_then_next_5_data(multi_file_session):
    """Test 21 & 22: First 5 rows followed by next 5 rows."""
    session_id, _, _ = multi_file_session
    res1 = agent_orchestrator.process_query(session_id, "Give me the first 5 rows.")
    assert res1["table"]["rows"][0][0] == "Laptop Pro"

    res2 = agent_orchestrator.process_query(session_id, "Now give me the next 5.")
    assert res2["table"]["rows"][0][0] == "Headphones"  # Row 6 in source


def test_conversation_reference_that_pdf(multi_file_session):
    """Test 23: Reference 'that PDF' uses the active document."""
    session_id, _, _ = multi_file_session
    # First interact with DSA PDF
    agent_orchestrator.process_query(session_id, "Summarize the DSA PDF")
    # Follow up
    res = agent_orchestrator.process_query(session_id, "What are the main algorithms in that PDF?")
    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert any("DSA" in c.get("file_name", "") for c in res["citations"])


def test_conversation_reference_the_spreadsheet(multi_file_session):
    """Test 24: Reference 'the spreadsheet' resolves to active dataset."""
    session_id, _, _ = multi_file_session
    res = agent_orchestrator.process_query(session_id, "What are the first 5 rows in the spreadsheet?")
    assert res["table"] is not None
    assert res["table"]["row_count"] == 5


def test_conversation_multiple_uploaded_files_isolation(multi_file_session):
    """Test 25: Disambiguates between multiple uploaded files cleanly."""
    session_id, _, _ = multi_file_session
    # Specifically target DSA PDF among sales.csv, DSA PDF, and annual_report.pdf
    res = agent_orchestrator.process_query(session_id, "Give me the first 5 questions from the DSA PDF.")
    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert any("DSA" in c.get("file_name", "") for c in res["citations"])
    assert not any("annual_report" in c.get("file_name", "") for c in res["citations"])


# ============================================================
# MANUAL ACCEPTANCE TESTS (Requirement 25, Tests 1 to 10)
# ============================================================

def test_manual_acceptance_criteria_1_to_10(multi_file_session):
    """
    Executes the exact 10 acceptance scenarios specified in Requirement 25.
    """
    session_id, _, _ = multi_file_session

    # TEST 1: "Give me the first 5 rows from the Excel file."
    # Expected: Actual table with exactly 5 rows in source order.
    t1 = agent_orchestrator.process_query(session_id, "Give me the first 5 rows from the Excel file.")
    assert t1["table"] is not None
    assert t1["table"]["row_count"] == 5
    assert len(t1["table"]["rows"]) == 5
    assert t1["table"]["rows"][0][0] == "Laptop Pro"

    # TEST 2: "Give me the top 5 products by revenue."
    # Expected: Actual table sorted by revenue descending.
    t2 = agent_orchestrator.process_query(session_id, "Give me the top 5 products by revenue.")
    assert t2["table"] is not None
    assert t2["table"]["row_count"] == 5
    rev_idx = t2["table"]["columns"].index("Revenue") if "Revenue" in t2["table"]["columns"] else (
        t2["table"]["columns"].index("metric") if "metric" in t2["table"]["columns"] else 1
    )
    t2_revs = [float(str(r[rev_idx]).replace(",", "")) for r in t2["table"]["rows"]]
    assert t2_revs == sorted(t2_revs, reverse=True)

    # TEST 3: "Give me the first 5 questions from the DSA PDF."
    # Expected: Exactly 5 questions in document order.
    t3 = agent_orchestrator.process_query(session_id, "Give me the first 5 questions from the DSA PDF.")
    assert t3["table"] is not None
    assert t3["table"]["row_count"] == 5
    assert "21" in str(t3["table"]["rows"][0][0])
    assert "25" in str(t3["table"]["rows"][4][0])

    # TEST 4: "Give me all 10 DSA questions."
    # Expected: Exactly 10 questions.
    t4 = agent_orchestrator.process_query(session_id, "Give me all 10 DSA questions.")
    assert t4["table"] is not None
    assert t4["table"]["row_count"] == 10
    assert "21" in str(t4["table"]["rows"][0][0])
    assert "30" in str(t4["table"]["rows"][9][0])

    # TEST 5: "Give me questions 21 to 30."
    # Expected: Questions 21-30 in order.
    t5 = agent_orchestrator.process_query(session_id, "Give me questions 21 to 30.")
    assert t5["table"] is not None
    assert t5["table"]["row_count"] == 10
    assert "21" in str(t5["table"]["rows"][0][0])
    assert "30" in str(t5["table"]["rows"][9][0])

    # TEST 6: "Now give me the next 5."
    # Expected: Next 5 after the previously returned items.
    # Start fresh sequence with first 5 questions
    agent_orchestrator.process_query(session_id, "Give me the first 5 questions from the DSA PDF.")
    t6 = agent_orchestrator.process_query(session_id, "Now give me the next 5.")
    assert t6["table"] is not None
    assert t6["table"]["row_count"] == 5
    assert "26" in str(t6["table"]["rows"][0][0])
    assert "30" in str(t6["table"]["rows"][4][0])

    # TEST 7: "What does the DSA PDF say about binary search?"
    # Expected: PDF retrieval only.
    t7 = agent_orchestrator.process_query(session_id, "What does the DSA PDF say about binary search?")
    assert t7["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert any("DSA" in c.get("file_name", "") for c in t7["citations"])
    assert not any(s.get("source_type") == "web" for s in t7.get("sources", []))

    # TEST 8: "Find 5 recent research papers about binary search optimization."
    # Expected: Research Agent + web search.
    t8 = agent_orchestrator.process_query(session_id, "Find 5 recent research papers about binary search optimization.")
    assert t8["intent"] == IntentType.RESEARCH.value
    assert len(t8.get("sources", [])) > 0

    # TEST 9: "Read the DSA PDF and find recent research papers about the concepts in it."
    # Expected: Document retrieval + Research Agent.
    t9 = agent_orchestrator.process_query(session_id, "Read the DSA PDF and find recent research papers about the concepts in it.")
    assert t9["intent"] == IntentType.HYBRID.value
    assert any(c.get("citation_type") == "pdf" for c in t9["citations"])
    assert any(c.get("citation_type") == "web" for c in t9["citations"])

    # TEST 10: "Analyze my sales Excel file and find research explaining why revenue changed."
    # Expected: Data tools + Research Agent.
    t10 = agent_orchestrator.process_query(session_id, "Analyze my sales Excel file and find research explaining why revenue changed.")
    assert t10["intent"] == IntentType.HYBRID.value
    assert any(c.get("citation_type") == "dataset" for c in t10["citations"])
    assert any(c.get("citation_type") == "web" for c in t10["citations"])
