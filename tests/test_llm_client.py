import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from app.agents.llm_client import LLMClient


def test_llm_client_unconfigured():
    """Verify behavior when no API key is provided."""
    client = LLMClient(api_key=None)
    assert client.is_available is False
    assert client.chat_model is None
    assert client.generate_content("Hello") is None
    assert client.generate_content("Hello", system_instruction="Be helpful") is None


def test_llm_client_initialization_failure():
    """Verify graceful degradation when ChatGoogleGenerativeAI raises during init."""
    with patch("langchain_google_genai.ChatGoogleGenerativeAI", side_effect=Exception("Auth error")):
        client = LLMClient(api_key="invalid_test_key")
        assert client.is_available is False
        assert client.chat_model is None
        assert client.generate_content("Hello") is None


def test_llm_client_configured_properties():
    """Verify client properties when successfully initialized."""
    with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_chat_class:
        mock_instance = MagicMock()
        mock_chat_class.return_value = mock_instance
        
        client = LLMClient(api_key="test_key_123", model_name="gemini-3.8-flash")
        assert client.is_available is True
        assert client.chat_model is mock_instance
        assert client.model_name == "gemini-3.8-flash"


def test_llm_client_generate_content_without_system_instruction():
    """Verify generate_content prompt execution via LangChain runnable."""
    client = LLMClient(api_key=None)
    
    # Mock chat model runnable that returns an AIMessage
    mock_runnable = RunnableLambda(lambda prompt_val: AIMessage(content="Generated answer"))
    client._chat_model = mock_runnable
    
    assert client.is_available is True
    res = client.generate_content("Explain gravity")
    assert res == "Generated answer"


def test_llm_client_generate_content_with_system_instruction():
    """Verify generate_content with system_instruction."""
    client = LLMClient(api_key=None)
    
    captured_messages = []
    def fake_invoke(prompt_val):
        msgs = prompt_val.to_messages()
        captured_messages.extend(msgs)
        return AIMessage(content="Structured answer with system prompt")
    
    client._chat_model = RunnableLambda(fake_invoke)
    
    res = client.generate_content(
        prompt="Tell me a joke",
        system_instruction="You are a stand-up comedian."
    )
    assert res == "Structured answer with system prompt"
    assert len(captured_messages) == 2
    assert captured_messages[0].content == "You are a stand-up comedian."
    assert captured_messages[1].content == "Tell me a joke"


def test_llm_client_generate_content_provider_error():
    """Verify that provider failures during invoke return None and do not crash."""
    client = LLMClient(api_key=None)
    
    def failing_invoke(prompt_val):
        raise RuntimeError("Quota exceeded or connection timed out")
    
    client._chat_model = RunnableLambda(failing_invoke)
    
    res = client.generate_content("Hello")
    assert res is None
