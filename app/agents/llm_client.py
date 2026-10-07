from typing import Optional, List, Dict, Any
from app.utils.config import settings
from app.utils.logger import logger


class LLMClient:
    """
    Client interface for Google Gemini API via google-genai SDK.
    Gracefully degrades when API key is not configured.
    """

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model_name = settings.GEMINI_MODEL
        self._client = None
        
        if self.api_key:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                logger.info(f"Initialized Gemini LLM client with model {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not initialize Gemini Client: {e}")

    @property
    def is_available(self) -> bool:
        return self._client is not None

    def generate_content(self, prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
        if not self.is_available:
            return None
        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                system_instruction=system_instruction
            ) if system_instruction else None
            
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            return response.text
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            return None


llm_client = LLMClient()
