from typing import Dict, Any
from app.tools.base import BaseTool
from app.services.web_fetch_service import web_fetch_service
from app.utils.logger import logger


class WebFetchTool(BaseTool):
    """
    Fetches readable text content and metadata from a specific webpage or paper URL.
    Enforces SSRF prevention, timeouts, and character caps.
    """
    name = "web_fetch"
    description = (
        "Fetch and extract readable text from a selected webpage or paper URL. "
        "Use this tool after web_search to read deep technical details or paper content."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full HTTP/HTTPS URL of the webpage or paper to fetch."
            }
        },
        "required": ["url"]
    }
    output_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "title": {"type": "string"},
            "text": {"type": "string"},
            "metadata": {"type": "object"},
            "source_type": {"type": "string"},
            "content_length": {"type": "integer"}
        }
    }
    usage_example = {
        "url": "https://arxiv.org/abs/2310.03743"
    }

    def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        url = kwargs.get("url", "")
        return web_fetch_service.fetch_url(url)
