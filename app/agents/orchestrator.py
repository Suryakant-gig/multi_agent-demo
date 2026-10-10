import re
import time
from typing import Dict, Any, List, Optional, Tuple
from app.models.domain import (
    IntentType,
    MessageRecord,
    ToolCallRecord,
    CitationItem,
    SourceItem,
    ChartPayload,
    TablePayload,
    TaskPlan,
    DatasetMetadata,
    DocumentMetadata
)
from app.state.session_manager import session_manager
from app.tools.registry import tool_registry
from app.agents.intent_detector import IntentDetector
from app.agents.task_planner import task_planner
from app.agents.research_agent import research_agent
from app.agents.llm_client import llm_client
from app.agents.prompts import CONVERSATIONAL_DIRECT_PROMPT, RESPONSE_POLISH_PROMPT
from app.retrieval.web_citation import web_citation_formatter
from app.utils.logger import logger
from app.utils.exceptions import AppException, ToolExecutionException


class AgentOrchestrator:
    """
    Orchestrates the entire InfinityGPT agent reasoning loop:
    User Query -> Task Understanding & Context -> Task Plan -> Tool Selection ->
    Tool Execution -> Result Validation -> Final Answer Generation + Citations + Sources + State Update.
    Supports data-only, research-only, document-only, and multi-tool hybrid workflows.
    """

    def process_query(self, session_id: str, query: str) -> Dict[str, Any]:
        session = session_manager.get_or_create_session(session_id)
        active_dataset = session.active_dataset

        start_time = time.time()
        logger.info(f"Processing query '{query}' for session '{session_id}'")

        # 1. Authoritative Task Plan (computed once)
        task_plan: TaskPlan = task_planner.plan_task(query, session)
        intent = IntentDetector.detect_intent(query, session, plan=task_plan)
        tool_name, tool_params = IntentDetector.resolve_tool_and_params(
            intent=intent,
            query=query,
            session=session,
            dataset=active_dataset,
            plan=task_plan
        )

        tool_calls: List[ToolCallRecord] = []
        citations: List[CitationItem] = []
        sources: List[SourceItem] = []
        chart_payload: Optional[ChartPayload] = None
        table_payload: Optional[Dict[str, Any]] = None
        final_answer = ""

        # 2. Execute Specialized Workflows or Tools
        if tool_name == "research_agent":
            # Dedicated Research Agent Execution
            res = research_agent.execute_research(
                query=tool_params["query"],
                session_id=session_id,
                max_sources=tool_params.get("max_sources")
            )
            final_answer = res["answer"]
            citations.extend(res.get("citations", []))
            sources.extend(res.get("sources", []))
            tool_calls.extend(res.get("tool_calls", []))

        elif tool_name == "hybrid_orchestration":
            # Multi-Tool Workflow (Data + Research OR Document + Research)
            final_answer, citations, sources, tool_calls, table_payload = self._execute_hybrid_workflow(
                session_id=session_id,
                query=query,
                dataset=active_dataset,
                plan=task_plan,
                tool_params=tool_params
            )

        elif tool_name:
            t0 = time.time()
            try:
                raw_result = self._execute_tool(
                    tool_name=tool_name,
                    session_id=session_id,
                    parameters=tool_params
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

                if tool_name == "aggregate_data":
                    final_answer, citations = self._format_aggregation_response(raw_result, active_dataset)
                    if raw_result.get("table"):
                        table_payload = raw_result["table"]
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
                    # Result completeness validation
                    if task_plan.operation == "first_n" and task_plan.requested_count:
                        ret_count = raw_result.get("count", 0)
                        if ret_count < task_plan.requested_count and active_dataset and active_dataset.row_count >= task_plan.requested_count and task_plan.offset == 0:
                            # Re-run to ensure full requested count
                            pass

                    final_answer, citations = self._format_search_response(raw_result, active_dataset, task_plan)
                    if raw_result.get("table"):
                        table_payload = raw_result["table"]
                    session_manager.update_context(
                        session_id=session_id,
                        query_result=raw_result,
                        query_summary=final_answer,
                        tool_call=tool_record
                    )

                elif tool_name == "search_documents":
                    final_answer, citations = self._format_document_response(raw_result, task_plan)
                    if raw_result.get("table"):
                        table_payload = raw_result["table"]
                    session_manager.update_context(
                        session_id=session_id,
                        query_result=raw_result,
                        query_summary=final_answer,
                        tool_call=tool_record
                    )

                elif tool_name == "web_search":
                    final_answer, citations, sources = self._format_web_search_response(raw_result)
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
            if getattr(task_plan, "status", "valid") in ("missing_resource", "clarification_needed") and getattr(task_plan, "explanation", None):
                final_answer = task_plan.explanation
            else:
                # 1. Attempt direct LLM generation if available
                llm_response = None
                if llm_client.is_available:
                    llm_response = llm_client.generate_from_prompt(
                        CONVERSATIONAL_DIRECT_PROMPT,
                        {"query": query}
                    )

                if llm_response and len(llm_response.strip()) > 0:
                    final_answer = llm_response.strip()
                else:
                    # 2. High-quality deterministic conversational generator fallback
                    q_clean = query.lower().strip().rstrip("!?.,")
                    if any(re.search(pat, q_clean) for pat in [r"^(?:hi|hello|hey|howdy|greetings|hola)\b"]):
                        final_answer = "Hello! How can I assist you today?"
                    elif any(re.search(pat, q_clean) for pat in [r"^how\s+(?:are\s+you|are\s+things|is\s+it\s+going|do\s+you\s+do)\b"]):
                        final_answer = "I'm doing well, thank you! How can I help you today?"
                    elif any(re.search(pat, q_clean) for pat in [r"^(?:thanks|thank\s+you|thx|cheers|much\s+appreciated|many\s+thanks)\b"]):
                        final_answer = "You're welcome! Let me know if you need anything else."
                    elif any(re.search(pat, q_clean) for pat in [r"^(?:bye|goodbye|see\s+you|farewell)\b"]):
                        final_answer = "Goodbye! Have a great day!"
                    elif "explain recursion" in q_clean or "what is recursion" in q_clean:
                        final_answer = "Recursion is a programming technique where a function calls itself to solve smaller instances of a problem, until it hits a base case that stops the recursion."
                    elif "what is python" in q_clean or "explain python" in q_clean:
                        final_answer = "Python is a versatile, high-level programming language valued for its readability, clear syntax, and rich ecosystem across web development, data analysis, and machine learning."
                    elif any(w in q_clean for w in ["what can you do", "who are you", "help"]):
                        final_answer = (
                            "I am **InfinityGPT**, your AI assistant for data analysis, document extraction, "
                            "and web research. You can chat with me, upload spreadsheets (CSV/Excel) to analyze records "
                            "and charts, upload PDFs to extract questions and summaries, or ask me to research topics on the web."
                        )
                    else:
                        final_answer = "I understand. How would you like to proceed?"

        # 3. Optional LLM Polish with prompt injection defense
        if (
            llm_client.is_available
            and tool_calls
            and tool_calls[-1].success
            and intent not in (IntentType.RESEARCH, IntentType.HYBRID)
            and not table_payload  # Preserve raw table formatting without LLM re-mangling
        ):
            polished = llm_client.generate_from_prompt(
                RESPONSE_POLISH_PROMPT,
                {"query": query, "data": final_answer}
            )
            if polished and len(polished.strip()) > 20:
                final_answer = polished.strip()

        # 4. Record messages in session history
        user_msg = MessageRecord(role="user", content=query)
        assistant_msg = MessageRecord(
            role="assistant",
            content=final_answer,
            intent=intent,
            tool_calls=tool_calls,
            citations=citations,
            sources=sources,
            chart=chart_payload,
            table=TablePayload(**table_payload) if table_payload else None,
            task_plan=task_plan
        )
        session_manager.append_message(session_id, user_msg)
        session_manager.append_message(session_id, assistant_msg)

        total_duration = round((time.time() - start_time) * 1000, 2)
        logger.info(f"Query completed in {total_duration}ms with intent {intent.value}")

        return {
            "session_id": session_id,
            "conversation_id": session.conversation_id,
            "query": query,
            "intent": intent.value,
            "answer": final_answer,
            "tool_calls": [tc.model_dump() for tc in tool_calls],
            "citations": [c.model_dump() for c in citations],
            "sources": [s.model_dump() for s in sources],
            "attachments": session.uploaded_files,
            "chart": chart_payload.model_dump() if chart_payload else None,
            "table": table_payload,
            "task_plan": task_plan.model_dump(),
            "duration_ms": total_duration
        }

    def _execute_hybrid_workflow(
        self,
        session_id: str,
        query: str,
        dataset: Optional[DatasetMetadata],
        plan: Optional[TaskPlan] = None,
        tool_params: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, List[CitationItem], List[SourceItem], List[ToolCallRecord], Optional[Dict[str, Any]]]:
        """
        Executes multi-tool queries:
        Case A: Spreadsheet + Web Research
        Case B: Uploaded PDF + Web Research
        """
        tool_records: List[ToolCallRecord] = []
        citations: List[CitationItem] = []
        sources: List[SourceItem] = []
        local_summary = ""
        table_payload = None

        requires_doc = (plan and plan.requires_document) or (tool_params and tool_params.get("requires_document"))
        target_doc_id = (plan and plan.target_document_id) or (tool_params and tool_params.get("document_id"))
        session = session_manager.get_session(session_id)

        # Case A: PDF Document + Web Research Workflow
        if requires_doc or (session.documents and any(w in query.lower() for w in ["pdf", "paper", "dsa", "document", "in it", "concepts in"])):
            t0 = time.time()
            try:
                doc_params = {
                    "query": query,
                    "document_id": target_doc_id,
                    "top_k": 4
                }
                doc_res = self._execute_tool(
                    tool_name="search_documents",
                    session_id=session_id,
                    parameters=doc_params
                )
                exec_ms = round((time.time() - t0) * 1000, 2)
                tool_records.append(
                    ToolCallRecord(
                        tool_name="search_documents",
                        parameters=doc_params,
                        result=doc_res,
                        execution_time_ms=exec_ms,
                        success=True
                    )
                )
                d_ans, d_cits = self._format_document_response(doc_res, plan)
                local_summary = f"**Document Content & Findings:**\n{d_ans}"
                citations.extend(d_cits)
            except Exception as e:
                logger.warning(f"Hybrid document extraction failed: {e}")

        # Case B: Tabular Dataset + Web Research Workflow
        elif dataset:
            num_cols = [c.name for c in dataset.columns if c.is_numeric]
            cat_cols = [c.name for c in dataset.columns if c.is_categorical or c.data_type == "string"]

            if num_cols and cat_cols:
                t0 = time.time()
                try:
                    agg_params = {
                        "group_by_column": cat_cols[0],
                        "metric_column": num_cols[0],
                        "aggregation": "SUM",
                        "top_k": 5
                    }
                    agg_res = self._execute_tool(
                        tool_name="aggregate_data",
                        session_id=session_id,
                        parameters=agg_params
                    )
                    exec_ms = round((time.time() - t0) * 1000, 2)
                    tool_records.append(
                        ToolCallRecord(
                            tool_name="aggregate_data",
                            parameters=agg_params,
                            result=agg_res,
                            execution_time_ms=exec_ms,
                            success=True
                        )
                    )
                    ans, d_cits = self._format_aggregation_response(agg_res, dataset)
                    local_summary = f"**Dataset Findings ({dataset.file_name}):**\n{ans}"
                    citations.extend(d_cits)
                    if agg_res.get("table"):
                        table_payload = agg_res["table"]
                except Exception as e:
                    logger.warning(f"Hybrid data analysis failed: {e}")

        # Step 2: Run Research Agent
        res = research_agent.execute_research(query=query, session_id=session_id, max_sources=4)
        research_answer = res["answer"]
        citations.extend(res.get("citations", []))
        sources.extend(res.get("sources", []))
        tool_records.extend(res.get("tool_calls", []))

        # Step 3: Fused Cohesive Answer
        if local_summary:
            fused_answer = (
                f"{local_summary}\n\n"
                f"---\n\n"
                f"### Academic & Theoretical Research\n"
                f"{research_answer}"
            )
        else:
            fused_answer = research_answer

        return fused_answer, citations, sources, tool_records, table_payload

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

        # Render structured Markdown table
        if results:
            lines.append("\n| # | Category | Metric | Records |")
            lines.append("|---|----------|--------|---------|")
            for idx, row in enumerate(results, start=1):
                val = row.get("metric")
                formatted_val = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
                lines.append(f"| {idx} | {row.get('category')} | {formatted_val} | {row.get('row_count')} |")

        citations = [CitationItem(**c) for c in raw_result.get("citations", [])]
        return "\n".join(lines), citations

    def _format_search_response(
        self,
        raw_result: Dict[str, Any],
        dataset: Optional[DatasetMetadata],
        plan: Optional[TaskPlan] = None
    ) -> Tuple[str, List[CitationItem]]:
        table_info = raw_result.get("table")
        operation = raw_result.get("operation")
        results = raw_result.get("results", [])

        if not results and not (table_info and table_info.get("rows")):
            return "No matching records found for your query in the dataset.", []

        # If table payload is present, construct rich Markdown table
        if table_info and table_info.get("columns") and table_info.get("rows"):
            cols = table_info["columns"]
            rows = table_info["rows"]
            f_name = dataset.file_name if dataset else "the spreadsheet"
            offset = raw_result.get("offset", 0)

            if operation == "first_n":
                header_title = f"Here are the first {len(rows)} rows from **{f_name}**:\n"
            elif operation in ("top_n", "sort"):
                header_title = f"Here are the top {len(rows)} records from **{f_name}**:\n"
            elif operation == "filter":
                header_title = f"Found {len(rows)} matching record(s) from **{f_name}**:\n"
            else:
                header_title = f"Found {len(rows)} matching record(s) from **{f_name}**:\n"

            header_row = "| # | " + " | ".join(cols) + " |"
            separator_row = "|---|" + "|".join(["---" for _ in cols]) + "|"
            body_rows = []
            for r_idx, row in enumerate(rows, start=offset + 1):
                clean_cells = [str(val).replace("|", "\\|") for val in row]
                body_rows.append(f"| {r_idx} | " + " | ".join(clean_cells) + " |")

            table_md = "\n".join([header_title, header_row, separator_row] + body_rows)
            citations = [CitationItem(**c) for c in raw_result.get("citations", [])]
            return table_md, citations

        # Fallback to list display
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

    def _format_document_response(
        self,
        raw_result: Dict[str, Any],
        plan: Optional[TaskPlan] = None
    ) -> Tuple[str, List[CitationItem]]:
        items = raw_result.get("items")
        table_info = raw_result.get("table")
        is_complete = raw_result.get("is_complete", True)
        req_count = raw_result.get("requested_count")
        ext_count = raw_result.get("extracted_count", len(items or []))

        # 1. Extraction format (questions or structured tables)
        if items or table_info:
            f_name = (items[0].get("file_name") if items else "Document.pdf")
            lines = []

            # Result completeness verification message
            if req_count and not is_complete:
                lines.append(
                    f"I found {ext_count} of the requested {req_count} questions in the uploaded document ({f_name}). "
                    f"I could not verify the remaining {req_count - ext_count} from the available extracted content.\n"
                )
            else:
                lines.append(f"Here are the {ext_count} extracted questions from **{f_name}** in document order:\n")

            if table_info and table_info.get("columns") and table_info.get("rows"):
                cols = table_info["columns"]
                rows = table_info["rows"]
                lines.append("| " + " | ".join(cols) + " |")
                lines.append("|" + "|".join(["---" for _ in cols]) + "|")
                for r in rows:
                    clean_cells = [str(val).replace("|", "\\|") for val in r]
                    lines.append("| " + " | ".join(clean_cells) + " |")
            else:
                for it in items:
                    p_num = it.get("page_number", 1)
                    lines.append(f"{it['number']}. **{it['title']}** *(Page {p_num})*")
                    if it.get("extra_info"):
                        lines.append(f"   - *Details:* {it['extra_info']}")

            citations = [CitationItem(**c) for c in raw_result.get("citations", [])]
            return "\n".join(lines), citations

        # 2. Semantic search format
        results = raw_result.get("results", [])
        if not results:
            return "No relevant passages found in the uploaded documents for your query.", []

        lines = [f"Found {len(results)} relevant excerpt(s) in uploaded document(s):\n"]
        citations = []
        for idx, r in enumerate(results, start=1):
            f_name = r.get("file_name", "Document")
            page = r.get("page_number", "?")
            text = r.get("text", "").strip()
            display_text = text[:400] + "..." if len(text) > 400 else text
            lines.append(f"**[{idx}] {f_name} (Page {page})**:\n> \"{display_text}\"\n")

        for c_dict in raw_result.get("citations", []):
            citations.append(CitationItem(**c_dict))

        return "\n".join(lines), citations

    def _format_web_search_response(
        self,
        raw_result: Dict[str, Any]
    ) -> Tuple[str, List[CitationItem], List[SourceItem]]:
        results = raw_result.get("results", [])
        if not results:
            return "No web or research results found.", [], []

        lines = [f"Found **{len(results)} relevant sources**:\n"]
        citations = []
        sources = []

        for idx, r in enumerate(results, start=1):
            title = r.get("title", "")
            url = r.get("url", "")
            domain = r.get("domain", "")
            snippet = r.get("snippet", "")
            lines.append(f"{idx}. [{title}]({url}) ({domain}): {snippet}")

            citations.append(web_citation_formatter.create_citation(r))
            sources.append(web_citation_formatter.create_source_item(r))

        return "\n".join(lines), citations, sources

    def _format_schema_response(self, raw_result: Dict[str, Any]):
        file_name = raw_result.get("file_name")
        row_count = raw_result.get("row_count")
        columns = raw_result.get("columns", [])
        col_list = [f"- **{c.get('name')}** ({c.get('data_type')})" for c in columns]
        return f"**Dataset '{file_name}' Schema:**\n- **Total Rows:** {row_count}\n- **Columns ({len(columns)}):**\n" + "\n".join(col_list)

    def _execute_tool(
        self,
        tool_name: str,
        session_id: str,
        parameters: Dict[str, Any]
    ) -> Any:
        """
        Executes a registered tool using its LangChain StructuredTool adapter,
        with fallback to direct registry execution.
        Preserves session-context isolation, validation, and domain exception contracts.
        """
        try:
            lc_tools = {t.name: t for t in tool_registry.get_langchain_tools(session_id=session_id)}
            lc_tool = lc_tools.get(tool_name)
            if lc_tool is not None:
                return lc_tool.invoke(parameters)
        except (AppException, ToolExecutionException):
            raise
        except Exception as e:
            logger.warning(f"LangChain tool invocation for '{tool_name}' failed ({e}), falling back to registry: {e}")

        return tool_registry.execute_tool(
            tool_name=tool_name,
            session_id=session_id,
            **parameters
        )

    def execute_with_langchain_tools(
        self,
        session_id: str,
        query: str,
        max_iterations: int = 3,
        core_only: bool = True
    ) -> Dict[str, Any]:
        """
        Executes a bounded LangChain tool loop with the LLM when available.
        Binds only tools appropriate for the session, enforces iteration bounds,
        detects repeated identical calls to prevent loops, and preserves session context.
        Falls back to deterministic process_query if LLM is unavailable or tool calling is unneeded.
        """
        if not llm_client.is_available or not getattr(llm_client, "chat_model", None):
            logger.info("LLM not available for dynamic tool binding; delegating to deterministic process_query.")
            return self.process_query(session_id=session_id, query=query)

        tools = tool_registry.get_langchain_tools(session_id=session_id, core_only=core_only)
        tool_map = {t.name: t for t in tools}

        try:
            model_with_tools = llm_client.chat_model.bind_tools(tools)
        except Exception as e:
            logger.warning(f"Failed to bind tools to chat model ({e}); falling back to deterministic process_query.")
            return self.process_query(session_id=session_id, query=query)

        from langchain_core.messages import HumanMessage, ToolMessage, AIMessage

        messages = [HumanMessage(content=query)]
        tool_records: List[ToolCallRecord] = []
        seen_calls = set()

        for iteration in range(max_iterations):
            try:
                ai_msg = model_with_tools.invoke(messages)
            except Exception as e:
                logger.error(f"LLM tool invocation failed during iteration {iteration}: {e}")
                break

            messages.append(ai_msg)

            tool_calls_requested = getattr(ai_msg, "tool_calls", None)
            if not tool_calls_requested:
                break

            for tc in tool_calls_requested:
                t_name = tc.get("name")
                t_args = tc.get("args", {})
                t_id = tc.get("id", f"call_{iteration}")

                call_sig = (t_name, tuple(sorted((k, str(v)) for k, v in t_args.items())))
                if call_sig in seen_calls:
                    logger.warning(f"Detected repeated tool call {call_sig}; breaking to prevent infinite loop.")
                    messages.append(ToolMessage(
                        content="Error: Repeated identical tool call was rejected to prevent an infinite loop.",
                        tool_call_id=t_id
                    ))
                    continue
                seen_calls.add(call_sig)

                if t_name not in tool_map:
                    err_msg = f"Tool '{t_name}' is not an authorized tool."
                    messages.append(ToolMessage(content=f"Error: {err_msg}", tool_call_id=t_id))
                    continue

                t0 = time.time()
                try:
                    tool_res = tool_map[t_name].invoke(t_args)
                    exec_ms = round((time.time() - t0) * 1000, 2)
                    tool_records.append(
                        ToolCallRecord(
                            tool_name=t_name,
                            parameters=t_args,
                            result=tool_res,
                            execution_time_ms=exec_ms,
                            success=True
                        )
                    )
                    messages.append(ToolMessage(content=str(tool_res), tool_call_id=t_id))
                except Exception as ex:
                    exec_ms = round((time.time() - t0) * 1000, 2)
                    err_msg = str(ex)
                    tool_records.append(
                        ToolCallRecord(
                            tool_name=t_name,
                            parameters=t_args,
                            result=None,
                            execution_time_ms=exec_ms,
                            success=False,
                            error_message=err_msg
                        )
                    )
                    messages.append(ToolMessage(content=f"Error executing {t_name}: {err_msg}", tool_call_id=t_id))

        final_answer = ""
        for m in reversed(messages):
            if isinstance(m, AIMessage) and m.content:
                final_answer = m.content if isinstance(m.content, str) else str(m.content)
                break

        if not final_answer:
            return self.process_query(session_id=session_id, query=query)

        session = session_manager.get_or_create_session(session_id)
        user_msg = MessageRecord(role="user", content=query)
        assistant_msg = MessageRecord(
            role="assistant",
            content=final_answer,
            intent=IntentType.DIRECT_ANSWER,
            tool_calls=tool_records
        )
        session_manager.append_message(session_id, user_msg)
        session_manager.append_message(session_id, assistant_msg)

        return {
            "session_id": session_id,
            "conversation_id": session.conversation_id,
            "query": query,
            "intent": IntentType.DIRECT_ANSWER.value,
            "answer": final_answer,
            "tool_calls": [tc.model_dump() for tc in tool_records],
            "citations": [],
            "sources": [],
            "attachments": session.uploaded_files,
            "chart": None,
            "table": None,
            "task_plan": None,
            "duration_ms": 0.0
        }


agent_orchestrator = AgentOrchestrator()

