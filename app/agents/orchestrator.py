import time
from typing import Dict, Any, List, Optional
from app.models.domain import IntentType, MessageRecord, ToolCallRecord, CitationItem, ChartPayload, DatasetMetadata
from app.state.session_manager import session_manager
from app.tools.registry import tool_registry
from app.agents.intent_detector import IntentDetector
from app.agents.llm_client import llm_client
from app.utils.logger import logger
from app.utils.exceptions import AppException, ToolExecutionException


class AgentOrchestrator:
    """
    Orchestrates the entire agent reasoning loop:
    User Query -> Session State -> Intent & Tool Selection -> Tool Execution ->
    Result Validation -> Final Answer Generation + Citations + State Update.
    """

    def process_query(self, session_id: str, query: str) -> Dict[str, Any]:
        session = session_manager.get_or_create_session(session_id)
        active_dataset = None
        if session.active_file_id and session.active_file_id in session.files:
            active_dataset = session.files[session.active_file_id]

        start_time = time.time()
        logger.info(f"Processing query '{query}' for session '{session_id}'")

        # 1. Determine Intent
        intent = IntentDetector.detect_intent(query, session)
        tool_name, tool_params = IntentDetector.resolve_tool_and_params(
            intent=intent,
            query=query,
            session=session,
            dataset=active_dataset
        )

        tool_calls: List[ToolCallRecord] = []
        citations: List[CitationItem] = []
        chart_payload: Optional[ChartPayload] = None
        final_answer = ""

        # 2. Execute Tool if required
        if tool_name:
            t0 = time.time()
            try:
                raw_result = tool_registry.execute_tool(
                    tool_name=tool_name,
                    session_id=session_id,
                    **tool_params
                )
                exec_ms = round((time.time() - t0) * 1000, 2)
                
                tool_record = ToolCallRecord(
                    tool_name=tool_name,
                    parameters=tool_params,
                    result=raw_result,
                    execution_time_ms=exec_ms,
                    success=True
                )
                tool_calls.append(tool_record)

                # Process tool results according to tool type
                if tool_name == "aggregate_data":
                    final_answer, citations = self._format_aggregation_response(raw_result, active_dataset)
                    session_manager.update_context(
                        session_id=session_id,
                        query_result=raw_result,
                        query_summary=final_answer,
                        tool_call=tool_record
                    )

                elif tool_name == "generate_chart":
                    chart_payload = ChartPayload(**raw_result)
                    final_answer = f"I have generated the {chart_payload.chart_type.value} chart: '{chart_payload.title}'."
                    if active_dataset:
                        citations.append(
                            CitationItem(
                                file_id=active_dataset.file_id,
                                file_name=active_dataset.file_name,
                                source_description=f"Source: {active_dataset.file_name} (Chart Visualization)"
                            )
                        )
                    session_manager.update_context(
                        session_id=session_id,
                        chart=chart_payload,
                        tool_call=tool_record
                    )

                elif tool_name == "search_data":
                    final_answer, citations = self._format_search_response(raw_result, active_dataset)
                    session_manager.update_context(
                        session_id=session_id,
                        query_result=raw_result,
                        query_summary=final_answer,
                        tool_call=tool_record
                    )

                elif tool_name == "inspect_schema":
                    final_answer = self._format_schema_response(raw_result)
                    session_manager.update_context(
                        session_id=session_id,
                        query_result=raw_result,
                        query_summary=final_answer,
                        tool_call=tool_record
                    )

                elif tool_name == "query_sql":
                    final_answer = f"Query executed successfully, returning {raw_result.get('row_count', 0)} rows."
                    for c_dict in raw_result.get("citations", []):
                        citations.append(CitationItem(**c_dict))
                    session_manager.update_context(
                        session_id=session_id,
                        query_result=raw_result,
                        query_summary=final_answer,
                        tool_call=tool_record
                    )

            except Exception as e:
                exec_ms = round((time.time() - t0) * 1000, 2)
                err_msg = str(e)
                logger.error(f"Tool execution failed: {err_msg}")
                tool_calls.append(
                    ToolCallRecord(
                        tool_name=tool_name,
                        parameters=tool_params,
                        result=None,
                        execution_time_ms=exec_ms,
                        success=False,
                        error_message=err_msg
                    )
                )
                final_answer = f"I encountered an issue executing tool '{tool_name}': {err_msg}"

        else:
            # Direct response without tool execution
            if not active_dataset:
                final_answer = (
                    "Welcome! Please upload an Excel (.xlsx, .xls) or CSV file first so I can analyze, "
                    "search, or visualize your data."
                )
            else:
                final_answer = (
                    f"Active dataset: '{active_dataset.file_name}' with {active_dataset.row_count} rows. "
                    "How can I help you analyze, search, or visualize it?"
                )

        # 3. Optional LLM Polish if Gemini is enabled and available
        if llm_client.is_available and tool_calls and tool_calls[-1].success:
            llm_prompt = (
                f"User Query: {query}\n"
                f"Data Result: {final_answer}\n"
                "Please provide a concise, professional answer to the user summarizing this data."
            )
            polished = llm_client.generate_content(llm_prompt)
            if polished:
                final_answer = polished.strip()

        # 4. Record messages in session history
        user_msg = MessageRecord(role="user", content=query)
        assistant_msg = MessageRecord(
            role="assistant",
            content=final_answer,
            intent=intent,
            tool_calls=tool_calls,
            citations=citations,
            chart=chart_payload
        )
        session_manager.append_message(session_id, user_msg)
        session_manager.append_message(session_id, assistant_msg)

        total_duration = round((time.time() - start_time) * 1000, 2)
        logger.info(f"Query completed in {total_duration}ms with intent {intent.value}")

        return {
            "session_id": session_id,
            "query": query,
            "intent": intent.value,
            "answer": final_answer,
            "tool_calls": [tc.model_dump() for tc in tool_calls],
            "citations": [c.model_dump() for c in citations],
            "chart": chart_payload.model_dump() if chart_payload else None,
            "duration_ms": total_duration
        }

    def _format_aggregation_response(self, raw_result: Dict[str, Any], dataset: Optional[DatasetMetadata]):
        group_col = raw_result.get("group_by_column")
        metric_col = raw_result.get("metric_column")
        agg = raw_result.get("aggregation")
        results = raw_result.get("results", [])
        top_k = raw_result.get("top_k", len(results))

        lines = [f"Here are the Top {min(top_k, len(results))} {group_col} by {agg}({metric_col}):\n"]
        for idx, row in enumerate(results, start=1):
            val = row.get("metric")
            formatted_val = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
            lines.append(f"{idx}. **{row.get('category')}**: {formatted_val} ({row.get('row_count')} records)")

        citations = [CitationItem(**c) for c in raw_result.get("citations", [])]
        return "\n".join(lines), citations

    def _format_search_response(self, raw_result: Dict[str, Any], dataset: Optional[DatasetMetadata]):
        results = raw_result.get("results", [])
        if not results:
            return "No matching records found for your query in the dataset.", []

        lines = [f"Found {len(results)} relevant result(s) (Top {len(results)}):\n"]
        citations = []
        for idx, item in enumerate(results, start=1):
            data = item.get("data", {})
            score = item.get("score")
            citation_dict = item.get("citation", {})
            summary = ", ".join([f"{k}: {v}" for k, v in list(data.items())[:4]])
            lines.append(f"{idx}. {summary} *(Relevance score: {score})*")
            if citation_dict:
                citations.append(CitationItem(**citation_dict))

        return "\n".join(lines), citations

    def _format_schema_response(self, raw_result: Dict[str, Any]):
        file_name = raw_result.get("file_name")
        row_count = raw_result.get("row_count")
        columns = raw_result.get("columns", [])
        col_list = [f"- **{c.get('name')}** ({c.get('data_type')})" for c in columns]
        return f"**Dataset '{file_name}' Schema:**\n- **Total Rows:** {row_count}\n- **Columns ({len(columns)}):**\n" + "\n".join(col_list)


agent_orchestrator = AgentOrchestrator()
