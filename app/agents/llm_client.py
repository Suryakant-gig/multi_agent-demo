from typing import Optional, Any, Dict
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.utils.config import settings
from app.utils.logger import logger


_UNSET = object()


class LLMClient:
    """
    Client interface for Google Gemini API via LangChain ChatGoogleGenerativeAI.
    Gracefully degrades when API key is not configured or initialization fails.
    """

    def __init__(self, api_key: Optional[str] = _UNSET, model_name: Optional[str] = None):
        if api_key is _UNSET:
            self.api_key = settings.GEMINI_API_KEY
        else:
            self.api_key = api_key
        self.model_name = model_name or settings.GEMINI_MODEL
        self._chat_model = None
        self._output_parser = StrOutputParser()
        
        if self.api_key:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                self._chat_model = ChatGoogleGenerativeAI(
                    model=self.model_name,
                    api_key=self.api_key,
                    timeout=30.0,
                    max_retries=2,
                )
                logger.info(f"Initialized LangChain Gemini chat model with model {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not initialize LangChain Gemini client: {e}")

    @property
    def is_available(self) -> bool:
        return self._chat_model is not None

    @property
    def chat_model(self) -> Optional[Any]:
        """Exposes the underlying LangChain BaseChatModel for agent / tool orchestration."""
        return self._chat_model

    def generate_content(self, prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
        """
        Executes a prompt through LangChain ChatPromptTemplate and ChatGoogleGenerativeAI,
        returning the parsed string response.
        """
        if not self.is_available:
            return None
        try:
            if system_instruction:
                prompt_template = ChatPromptTemplate.from_messages([
                    ("system", "{system_instruction}"),
                    ("human", "{prompt}"),
                ])
                chain = prompt_template | self._chat_model | self._output_parser
                response_text = chain.invoke({
                    "system_instruction": system_instruction,
                    "prompt": prompt
                })
            else:
                prompt_template = ChatPromptTemplate.from_messages([
                    ("human", "{prompt}"),
                ])
                chain = prompt_template | self._chat_model | self._output_parser
                response_text = chain.invoke({
                    "prompt": prompt
                })
            return response_text
        except Exception as e:
            logger.error(f"LangChain Gemini API call failed: {e}")
            return None

    def generate_from_prompt(self, prompt_template: ChatPromptTemplate, variables: Dict[str, Any]) -> Optional[str]:
        """
        Executes a LangChain ChatPromptTemplate with provided variables through ChatGoogleGenerativeAI
        and StrOutputParser.
        """
        if not self.is_available:
            return None
        try:
            chain = prompt_template | self._chat_model | self._output_parser
            return chain.invoke(variables)
        except Exception as e:
            logger.error(f"LangChain Gemini API call failed: {e}")
            return None


llm_client = LLMClient()
