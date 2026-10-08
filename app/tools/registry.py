from typing import Dict, List, Any, Optional
from app.tools.base import BaseTool
from app.tools.search_tool import SearchDataTool
from app.tools.aggregate_tool import AggregateDataTool
from app.tools.chart_tool import GenerateChartTool
from app.tools.schema_tool import InspectSchemaTool
from app.tools.sql_tool import QuerySQLTool
from app.tools.web_search_tool import WebSearchTool
from app.tools.web_fetch_tool import WebFetchTool
from app.tools.document_tool import SearchDocumentsTool
from app.utils.exceptions import ToolExecutionException


class ToolRegistry:
    """
    Central registry for all system tools.
    Manages tool discovery, schema generation for LLMs, and execution dispatch.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        default_tools = [
            SearchDataTool(),
            AggregateDataTool(),
            GenerateChartTool(),
            InspectSchemaTool(),
            QuerySQLTool(),
            WebSearchTool(),
            WebFetchTool(),
            SearchDocumentsTool()
        ]
        for tool in default_tools:
            self.register(tool)


    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise ToolExecutionException(name, f"Tool '{name}' is not registered.")
        return self._tools[name]

    def list_tools(self) -> List[BaseTool]:
        return list(self._tools.values())

    def get_tool_definitions(self, core_only: bool = True) -> List[Dict[str, Any]]:
        """Returns standard function-calling definitions for LLMs. If core_only=True, returns 5 core data tools."""
        if core_only:
            core_names = {"search_data", "aggregate_data", "generate_chart", "inspect_schema", "query_sql"}
            return [tool.to_function_definition() for name, tool in self._tools.items() if name in core_names]
        return [tool.to_function_definition() for tool in self._tools.values()]


    def execute_tool(self, tool_name: str, session_id: str, **kwargs) -> Dict[str, Any]:
        tool = self.get_tool(tool_name)
        return tool.run(session_id=session_id, **kwargs)


tool_registry = ToolRegistry()
