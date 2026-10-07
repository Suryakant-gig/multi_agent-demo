from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel
from app.utils.exceptions import ToolExecutionException
from app.utils.logger import logger


class BaseTool(ABC):
    """
    Abstract base class for all tools in the system.
    Strictly specifies schema, validation, error handling, and usage examples.
    """
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    usage_example: Dict[str, Any]

    def to_function_definition(self) -> Dict[str, Any]:
        """Returns standard OpenAI/Gemini compatible function calling tool declaration."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema
        }

    def validate_inputs(self, **kwargs) -> None:
        """Validates required parameters based on parameters_schema."""
        required_params = self.parameters_schema.get("required", [])
        for req in required_params:
            if req not in kwargs or kwargs[req] is None:
                raise ToolExecutionException(
                    self.name,
                    f"Missing required parameter '{req}'. Expected schema: {self.parameters_schema.get('properties', {}).get(req)}"
                )

    def run(self, session_id: str, **kwargs) -> Dict[str, Any]:
        """
        Executes tool with automatic validation and structured exception handling.
        """
        try:
            self.validate_inputs(**kwargs)
            return self.execute(session_id=session_id, **kwargs)
        except ToolExecutionException:
            raise
        except Exception as e:
            logger.error(f"Error in tool '{self.name}': {str(e)}", exc_info=True)
            raise ToolExecutionException(self.name, str(e), details={"input_params": kwargs})

    @abstractmethod
    def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        """Concrete execution logic implemented by each tool."""
        pass
