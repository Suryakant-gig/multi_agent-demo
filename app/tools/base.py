from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type, List
from pydantic import BaseModel, create_model, Field
from langchain_core.tools import StructuredTool
from app.utils.exceptions import ToolExecutionException
from app.utils.logger import logger


def _json_schema_to_py_type(prop_schema: Dict[str, Any]) -> Any:
    schema_type = prop_schema.get("type")
    if schema_type == "string":
        return str
    elif schema_type == "integer":
        return int
    elif schema_type == "number":
        return float
    elif schema_type == "boolean":
        return bool
    elif schema_type == "array":
        items = prop_schema.get("items", {})
        item_type = _json_schema_to_py_type(items) if items else Any
        return List[item_type]
    elif schema_type == "object":
        return Dict[str, Any]
    return Any


class BaseTool(ABC):
    """
    Abstract base class for all tools in the system.
    Strictly specifies schema, validation, error handling, and usage examples.
    Provides LangChain StructuredTool conversion for framework interoperability.
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

    def get_args_schema(self) -> Type[BaseModel]:
        """
        Dynamically constructs a Pydantic BaseModel representing the tool's input parameters
        from parameters_schema. Preserves field types, descriptions, defaults, and requirements.
        Caches the model class to ensure identity and avoid redundant class creation.
        """
        if getattr(self, "_args_schema", None) is None:
            props = self.parameters_schema.get("properties", {})
            required = set(self.parameters_schema.get("required", []))
            fields: Dict[str, Any] = {}

            for prop_name, prop_spec in props.items():
                py_type = _json_schema_to_py_type(prop_spec)
                desc = prop_spec.get("description", "")
                if prop_name in required and "default" not in prop_spec:
                    fields[prop_name] = (py_type, Field(..., description=desc))
                elif "default" in prop_spec:
                    fields[prop_name] = (py_type, Field(default=prop_spec["default"], description=desc))
                else:
                    fields[prop_name] = (Optional[py_type], Field(default=None, description=desc))

            self._args_schema = create_model(f"{self.name}_input", **fields)
        return self._args_schema

    def to_langchain_tool(self, session_id: Optional[str] = None) -> StructuredTool:
        """
        Converts this tool into a LangChain StructuredTool.
        Binds session_id to isolate request context from LLM arguments.
        Delegates execution directly to self.run(session_id=..., **kwargs).
        """
        args_schema = self.get_args_schema()

        def _invoke(**kwargs) -> Dict[str, Any]:
            target_session = session_id or kwargs.pop("session_id", None) or ""
            return self.run(session_id=target_session, **kwargs)

        _invoke.__doc__ = self.description

        return StructuredTool.from_function(
            func=_invoke,
            name=self.name,
            description=self.description,
            args_schema=args_schema,
            return_direct=False
        )

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
