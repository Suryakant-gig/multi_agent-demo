import pytest
from unittest.mock import patch, MagicMock
from app.state.session_manager import session_manager
from app.services.file_service import file_service
from app.documents.chunker import document_chunker
from app.documents.document_store import document_store
from app.agents.orchestrator import agent_orchestrator
from app.agents.task_planner import task_planner, TaskPlan
from app.agents.intent_detector import IntentDetector
from app.models.domain import IntentType


@pytest.fixture
def empty_session():
    """Session with no uploaded files or documents."""
    session_id = "test_empty_sess"
    session_manager.create_session(session_id)
    return session_id


@pytest.fixture
def pdf_only_session():
    """Session with only a PDF document uploaded."""
    session_id = "test_pdf_only_sess"
    session_manager.create_session(session_id)

    pages = [
        {"page_number": 1, "text": "Chapter 1: Introduction to Algorithms and Big O notation."},
        {"page_number": 2, "text": "Chapter 2: Data Structures including Arrays and Linked Lists."},
        {"page_number": 3, "text": "Chapter 3: Advanced Trees and Graph Traversals."},
        {"page_number": 10, "text": "Chapter 10: Dynamic Programming and Memoization on page 10."}
    ]
    chunks = document_chunker.chunk_document(
        document_id="doc_algo_book",
        file_name="algorithms_guide.pdf",
        pages=pages
    )
    document_store.store_chunks(session_id=session_id, chunks=chunks)
    session = session_manager.get_session(session_id)
    session.active_document_id = "doc_algo_book"
    return session_id, "doc_algo_book"


@pytest.fixture
def spreadsheet_only_session(tmp_path):
    """Session with only a tabular dataset uploaded."""
    session_id = "test_data_only_sess"
    session_manager.create_session(session_id)

    csv_file = tmp_path / "employee_salaries.csv"
    csv_content = """name,department,salary,experience
Alice,Engineering,120000,5
Bob,Engineering,140000,7
Charlie,Marketing,85000,3
Diana,Sales,95000,4
Evan,Marketing,90000,4
Fiona,Engineering,130000,6
George,Sales,105000,5
"""
    csv_file.write_text(csv_content, encoding="utf-8")
    dataset_meta = file_service.process_and_store_file(
        file_path=str(csv_file),
        original_filename="employee_salaries.csv",
        session_id=session_id
    )
    return session_id, dataset_meta


@pytest.fixture
def multi_resource_session(tmp_path):
    """Session with both a spreadsheet and a PDF report."""
    session_id = "test_multi_resource_sess"
    session_manager.create_session(session_id)

    # 1. Dataset
    csv_file = tmp_path / "sales_report.csv"
    csv_content = """Region,Revenue,Units
North,5000,50
South,3000,30
East,7000,70
West,4000,40
"""
    csv_file.write_text(csv_content, encoding="utf-8")
    dataset_meta = file_service.process_and_store_file(
        file_path=str(csv_file),
        original_filename="sales_report.csv",
        session_id=session_id
    )

    # 2. PDF
    pages = [
        {"page_number": 1, "text": "Annual Financial Report 2025: Revenue analysis across regions."}
    ]
    chunks = document_chunker.chunk_document(
        document_id="doc_annual_rep",
        file_name="annual_report.pdf",
        pages=pages
    )
    document_store.store_chunks(session_id=session_id, chunks=chunks)
    session = session_manager.get_session(session_id)
    session.active_document_id = "doc_annual_rep"
    return session_id, dataset_meta, "doc_annual_rep"


# ============================================================
# 1. CORE USER SCENARIOS (Testing and Validation 1-7)
# ============================================================

def test_scenario_1_hello_zero_tool_calls(empty_session):
    """Scenario 1: 'Hello' -> direct LLM response; zero tool calls."""
    res = agent_orchestrator.process_query(empty_session, "Hello")
    assert res["intent"] == IntentType.DIRECT_ANSWER.value
    assert len(res["tool_calls"]) == 0
    assert len(res["citations"]) == 0
    assert len(res["answer"]) > 0
    assert "hello" in res["answer"].lower() or "how can i assist" in res["answer"].lower()


def test_scenario_2_how_are_you_zero_tool_calls(pdf_only_session):
    """Scenario 2: 'How are you?' -> direct LLM response; zero tool calls (even with PDF uploaded)."""
    session_id, _ = pdf_only_session
    res = agent_orchestrator.process_query(session_id, "How are you?")
    assert res["intent"] == IntentType.DIRECT_ANSWER.value
    assert len(res["tool_calls"]) == 0
    assert len(res["citations"]) == 0
    assert "well" in res["answer"].lower() or "help" in res["answer"].lower()


def test_scenario_3_summarize_uploaded_pdf(pdf_only_session):
    """Scenario 3: 'Summarize my uploaded PDF' -> document search."""
    session_id, _ = pdf_only_session
    res = agent_orchestrator.process_query(session_id, "Summarize my uploaded PDF")
    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0]["tool_name"] == "search_documents"
    assert len(res["citations"]) > 0


def test_scenario_4_find_5_recent_research_papers(empty_session):
    """Scenario 4: 'Find 5 recent research papers' -> appropriate research tools."""
    mock_results = [
        {"title": f"Paper {i}", "url": f"https://arxiv.org/abs/2401.000{i}", "domain": "arxiv.org",
         "snippet": f"Groundbreaking research paper {i}", "published_at": "2024-01-01", "source_type": "paper"}
        for i in range(1, 6)
    ]
    with patch("app.services.web_search_service.web_search_service.search", return_value=mock_results):
        res = agent_orchestrator.process_query(empty_session, "Find 5 recent research papers about quantum computing")
        assert res["intent"] == IntentType.RESEARCH.value
        assert len(res.get("sources", [])) > 0
        assert any(tc["tool_name"] == "web_search" for tc in res["tool_calls"])


def test_scenario_5_give_me_recent_ai_news(empty_session):
    """Scenario 5: 'Give me recent AI news' -> web search."""
    mock_results = [
        {"title": "Latest AI Breakthrough", "url": "https://technews.com/ai-1", "domain": "technews.com",
         "snippet": "New AI models released this week", "published_at": "2024-02-01", "source_type": "article"}
    ]
    with patch("app.services.web_search_service.web_search_service.search", return_value=mock_results):
        res = agent_orchestrator.process_query(empty_session, "Give me recent AI news")
        assert res["intent"] == IntentType.WEB_SEARCH.value
        assert len(res["tool_calls"]) == 1
        assert res["tool_calls"][0]["tool_name"] == "web_search"
        assert len(res["citations"]) > 0


def test_scenario_6_page_10_of_my_pdf(pdf_only_session):
    """Scenario 6: 'What does page 10 of my PDF say?' -> targeted document retrieval."""
    session_id, _ = pdf_only_session
    res = agent_orchestrator.process_query(session_id, "What does page 10 of my PDF say?")
    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0]["tool_name"] == "search_documents"
    assert any(c.get("page_number") == 10 for c in res["citations"])
    assert "Dynamic Programming" in res["answer"] or "page 10" in res["answer"].lower()


def test_scenario_7_thanks_zero_tool_calls(spreadsheet_only_session):
    """Scenario 7: 'Thanks' -> direct LLM response; zero tool calls (even with spreadsheet uploaded)."""
    session_id, _ = spreadsheet_only_session
    res = agent_orchestrator.process_query(session_id, "Thanks")
    assert res["intent"] == IntentType.DIRECT_ANSWER.value
    assert len(res["tool_calls"]) == 0
    assert len(res["citations"]) == 0
    assert "welcome" in res["answer"].lower()


# ============================================================
# 2. MATRIX AND FALLBACK REGRESSION REQUIREMENTS
# ============================================================

def test_matrix_pdf_uploaded_explain_recursion(pdf_only_session):
    """PDF uploaded + 'Explain recursion' -> General answer, zero tool calls."""
    session_id, _ = pdf_only_session
    res = agent_orchestrator.process_query(session_id, "Explain recursion")
    assert res["intent"] == IntentType.DIRECT_ANSWER.value
    assert len(res["tool_calls"]) == 0
    assert len(res["citations"]) == 0
    assert "function" in res["answer"].lower() or "calls itself" in res["answer"].lower() or "base case" in res["answer"].lower()


def test_matrix_spreadsheet_uploaded_what_is_python(spreadsheet_only_session):
    """Spreadsheet uploaded + 'What is Python?' -> General answer, zero tool calls."""
    session_id, _ = spreadsheet_only_session
    res = agent_orchestrator.process_query(session_id, "What is Python?")
    assert res["intent"] == IntentType.DIRECT_ANSWER.value
    assert len(res["tool_calls"]) == 0
    assert len(res["citations"]) == 0
    assert "python" in res["answer"].lower()


def test_matrix_no_dataset_find_average_salary(empty_session):
    """No dataset + 'Find the average salary' -> Preserve data-analysis intent, report missing dataset."""
    res = agent_orchestrator.process_query(empty_session, "Find the average salary")
    assert res["intent"] == IntentType.DATA_ANALYSIS.value
    assert len(res["tool_calls"]) == 0
    assert "no dataset" in res["answer"].lower() or "please upload" in res["answer"].lower()


def test_matrix_no_pdf_summarize_chapter_3(empty_session):
    """No PDF + 'Summarize chapter 3 of my PDF' -> Preserve document intent, request document."""
    res = agent_orchestrator.process_query(empty_session, "Summarize chapter 3 of my PDF")
    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert len(res["tool_calls"]) == 0
    assert "no pdf" in res["answer"].lower() or "please upload" in res["answer"].lower()


def test_matrix_pdf_uploaded_summarize_chapter_3(pdf_only_session):
    """PDF uploaded + 'Summarize chapter 3' -> Uses the relevant PDF."""
    session_id, _ = pdf_only_session
    res = agent_orchestrator.process_query(session_id, "Summarize chapter 3")
    assert res["intent"] == IntentType.DOCUMENT_SEARCH.value
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0]["tool_name"] == "search_documents"
    assert "Chapter 3" in res["answer"] or "Trees" in res["answer"]


def test_matrix_spreadsheet_uploaded_calculate_average_salary(spreadsheet_only_session):
    """Spreadsheet uploaded + 'Calculate average salary' -> Analyzes the dataset."""
    session_id, _ = spreadsheet_only_session
    res = agent_orchestrator.process_query(session_id, "Calculate average salary by department")
    assert res["intent"] == IntentType.DATA_ANALYSIS.value
    assert len(res["tool_calls"]) == 1
    assert res["tool_calls"][0]["tool_name"] == "aggregate_data"


def test_matrix_hybrid_comparison(multi_resource_session):
    """PDF + Spreadsheet + 'Compare the salary figures in the spreadsheet with the report' -> Hybrid workflow."""
    session_id, _, _ = multi_resource_session
    mock_results = [{"title": "Market Study", "url": "https://example.com/study", "domain": "example.com", "snippet": "Study data"}]
    with patch("app.services.web_search_service.web_search_service.search", return_value=mock_results):
        res = agent_orchestrator.process_query(session_id, "Analyze my sales Excel file and find research explaining why revenue changed")
        assert res["intent"] == IntentType.HYBRID.value


# ============================================================
# 3. FOLLOW-UP AND PAGINATION TESTS
# ============================================================

def test_pagination_successive_pages(spreadsheet_only_session):
    """Pagination: 'first 3 rows' followed by 'show the next 3'."""
    session_id, _ = spreadsheet_only_session
    res1 = agent_orchestrator.process_query(session_id, "Give me the first 3 rows")
    assert res1["table"]["row_count"] == 3
    assert res1["table"]["rows"][0][0] == "Alice"

    # Turn 2: 'Show the next 3'
    res2 = agent_orchestrator.process_query(session_id, "Show the next 3")
    assert res2["table"] is not None
    assert res2["table"]["row_count"] == 3
    assert res2["table"]["rows"][0][0] == "Diana"


def test_pagination_unsupported_without_context(empty_session):
    """Pagination with missing/invalid previous state asks for clarification."""
    res = agent_orchestrator.process_query(empty_session, "Show the next 10")
    assert res["intent"] == IntentType.DIRECT_ANSWER.value
    assert len(res["tool_calls"]) == 0
    assert "not sure" in res["answer"].lower() or "specify" in res["answer"].lower()


# ============================================================
# 4. SINGLE AUTHORITATIVE PLANNING CALL VERIFICATION
# ============================================================

def test_single_authoritative_planning_call(pdf_only_session):
    """Verify TaskPlanner.plan_task is called exactly once per process_query execution."""
    session_id, _ = pdf_only_session
    with patch.object(task_planner, "plan_task", wraps=task_planner.plan_task) as mock_plan:
        agent_orchestrator.process_query(session_id, "What does page 10 say?")
        assert mock_plan.call_count == 1
