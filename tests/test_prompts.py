import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from app.agents.prompts import (
    CONVERSATIONAL_DIRECT_PROMPT,
    CONVERSATIONAL_DIRECT_SYSTEM,
    RESPONSE_POLISH_PROMPT,
    RESPONSE_POLISH_SYSTEM,
    RESEARCH_SYNTHESIS_PROMPT,
    RESEARCH_SYNTHESIS_SYSTEM,
    format_conversational_prompt,
    format_response_polish_prompt,
    format_research_synthesis_prompt,
)
from app.agents.llm_client import LLMClient


# ==============================================================================
# 1. Conversational Direct Prompt Tests
# ==============================================================================

def test_conversational_direct_prompt_variables():
    assert set(CONVERSATIONAL_DIRECT_PROMPT.input_variables) == {"query"}


def test_conversational_direct_prompt_rendering():
    prompt_val = CONVERSATIONAL_DIRECT_PROMPT.format_prompt(query="Hello there!")
    messages = prompt_val.to_messages()
    assert len(messages) == 2
    assert messages[0].content == CONVERSATIONAL_DIRECT_SYSTEM
    assert "InfinityGPT" in messages[0].content
    assert messages[1].content == "Hello there!"


def test_conversational_direct_prompt_missing_variable():
    with pytest.raises(KeyError):
        CONVERSATIONAL_DIRECT_PROMPT.format_messages()


# ==============================================================================
# 2. Response Polish Prompt Tests
# ==============================================================================

def test_response_polish_prompt_variables():
    assert set(RESPONSE_POLISH_PROMPT.input_variables) == {"query", "data"}


def test_response_polish_prompt_security_boundaries():
    sample_data = "Product: Laptop, Revenue: $5000"
    prompt_val = RESPONSE_POLISH_PROMPT.format_prompt(query="Show sales", data=sample_data)
    messages = prompt_val.to_messages()
    assert len(messages) == 2
    assert messages[0].content == RESPONSE_POLISH_SYSTEM
    human_content = messages[1].content

    # Security delimiters must be strictly preserved
    assert "<untrusted_data>" in human_content
    assert "</untrusted_data>" in human_content
    assert sample_data in human_content
    assert human_content.index("<untrusted_data>") < human_content.index(sample_data) < human_content.index("</untrusted_data>")


def test_response_polish_prompt_missing_variable():
    with pytest.raises(KeyError):
        RESPONSE_POLISH_PROMPT.format_messages(query="Show sales")


# ==============================================================================
# 3. Research Synthesis Prompt Tests
# ==============================================================================

def test_research_synthesis_prompt_variables():
    assert set(RESEARCH_SYNTHESIS_PROMPT.input_variables) == {"query", "goal", "evidence"}


def test_research_synthesis_prompt_security_boundaries_and_rules():
    sample_evidence = "Source [1]: Hybrid RAG, URL: https://arxiv.org/abs/2310.03743"
    prompt_val = RESEARCH_SYNTHESIS_PROMPT.format_prompt(
        query="Research RAG",
        goal="Analyze hybrid retrieval",
        evidence=sample_evidence
    )
    messages = prompt_val.to_messages()
    assert len(messages) == 2
    sys_content = messages[0].content
    human_content = messages[1].content

    # System grounding & security rules
    assert "CRITICAL SECURITY INSTRUCTIONS" in sys_content
    assert "<untrusted_evidence>" in sys_content
    assert "GROUNDING RULES" in sys_content
    assert "Never invent, hallucinate, or fabricate authors, publications" in sys_content
    assert "Every cited source must match the provided URLs exactly" in sys_content

    # Human security boundary
    assert "<untrusted_evidence>" in human_content
    assert "</untrusted_evidence>" in human_content
    assert sample_evidence in human_content
    assert human_content.index("<untrusted_evidence>") < human_content.index(sample_evidence) < human_content.index("</untrusted_evidence>")

    # Structure requirements
    assert "Executive Summary" in human_content
    assert "Key Methodologies & Findings" in human_content
    assert "Comparative Analysis / Benchmarks" in human_content


def test_research_synthesis_prompt_missing_variable():
    with pytest.raises(KeyError):
        RESEARCH_SYNTHESIS_PROMPT.format_messages(query="Research RAG", goal="Hybrid")


# ==============================================================================
# 4. Literal Braces & Code Injection Tests
# ==============================================================================

def test_prompts_handle_literal_braces_in_variables():
    """Ensure variables containing JSON, code, or template braces do not cause formatting errors."""
    code_evidence = '{"key": "value", "items": [1, 2, 3], "code": "def fn(): return {table}"}'
    prompt_val = RESEARCH_SYNTHESIS_PROMPT.format_prompt(
        query="Explain {json} syntax",
        goal="Parse {schema}",
        evidence=code_evidence
    )
    human_content = prompt_val.to_messages()[1].content
    assert code_evidence in human_content
    assert "{table}" in human_content


# ==============================================================================
# 5. LLM Client Integration with Prompts
# ==============================================================================

def test_llm_client_generate_from_prompt_success():
    client = LLMClient(api_key=None)
    client._chat_model = RunnableLambda(lambda prompt_val: AIMessage(content="LangChain synthesized response"))

    res = client.generate_from_prompt(
        CONVERSATIONAL_DIRECT_PROMPT,
        {"query": "Hello"}
    )
    assert res == "LangChain synthesized response"


def test_llm_client_generate_from_prompt_unconfigured():
    client = LLMClient(api_key=None)
    res = client.generate_from_prompt(
        CONVERSATIONAL_DIRECT_PROMPT,
        {"query": "Hello"}
    )
    assert res is None


def test_llm_client_generate_from_prompt_error_handling():
    client = LLMClient(api_key=None)
    client._chat_model = RunnableLambda(lambda p: (_ for _ in ()).throw(RuntimeError("API error")))

    res = client.generate_from_prompt(
        CONVERSATIONAL_DIRECT_PROMPT,
        {"query": "Hello"}
    )
    assert res is None


# ==============================================================================
# 6. Helper Function Validation Tests
# ==============================================================================

def test_prompt_helper_validation():
    with pytest.raises(ValueError, match="'query' variable cannot be empty"):
        format_conversational_prompt("")

    with pytest.raises(ValueError, match="'data' variable cannot be None"):
        format_response_polish_prompt("query", None)

    with pytest.raises(ValueError, match="'evidence' variable cannot be None"):
        format_research_synthesis_prompt("query", "goal", None)
