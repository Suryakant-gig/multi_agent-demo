import re
from typing import Dict, Any, Optional, Tuple, List
from app.models.domain import TaskPlan, TaskSource, IntentType, DatasetMetadata, DocumentMetadata
from app.state.state_models import ConversationState
from app.utils.logger import logger


class TaskPlanner:
    """
    Intelligent routing and task planning engine for InfinityGPT.
    Understands user intent, validates resources, disambiguates targets,
    and returns a structured TaskPlan without letting resource presence
    override unrelated queries.
    """

    SCHOLARLY_KEYWORDS = [
        "research", "research paper", "research papers", "papers about", "papers on", "arxiv",
        "literature", "survey", "studies", "scientific study", "academic",
        "recent developments in", "latest developments in", "recent research", "latest research",
        "recent papers", "latest papers"
    ]

    SPREADSHEET_KEYWORDS = [
        "spreadsheet", "excel", "csv", "row", "rows", "column", "columns", "record", "records",
        "dataset", "sales", "revenue", "data points", "first 5 rows", "first 10 rows",
        "top 5 records", "table above", "the spreadsheet", "salary"
    ]

    DOCUMENT_KEYWORDS = [
        "pdf", "document", "report", "paper i uploaded", "uploaded pdf", "attached pdf",
        "uploaded document", "this document", "this pdf", "dsa pdf", "questions in the pdf",
        "chapter", "abstract", "methodology"
    ]

    CONVERSATIONAL_PATTERNS = [
        r"^(?:hi|hello|hey|howdy|greetings|hola)\b",
        r"^good\s+(?:morning|afternoon|evening|day|night)\b",
        r"^how\s+(?:are\s+you|are\s+things|is\s+it\s+going|do\s+you\s+do)\b",
        r"^(?:thanks|thank\s+you|thx|cheers|much\s+appreciated|many\s+thanks)\b",
        r"^(?:bye|goodbye|see\s+you|farewell)\b",
        r"^(?:who\s+are\s+you|what\s+are\s+you|what\s+can\s+you\s+do)\b",
    ]

    WEB_SEARCH_KEYWORDS = [
        "search the internet", "search the web", "search online", "google search",
        "official docs", "official documentation", "browse the web", "web search"
    ]

    FOLLOWUP_COUNT_REGEX = re.compile(
        r"\b(?:(?:now\s+)?(?:give|show|get)\s+(?:me\s+)?(?:the\s+)?|now\s+)?next\s+(\d+)\b",
        re.IGNORECASE
    )
    FOLLOWUP_GENERIC_PATTERNS = [
        r"^(?:now\s+)?(?:give|show|get)\s+(?:me\s+)?(?:the\s+)?next\b",
        r"^(?:next|next\s+page|more|show\s+more|show\s+me\s+more|continue|get\s+more)\b",
    ]
    FOLLOWUP_WORDS = ["next", "next page", "show me more", "show more", "continue", "more", "now give me the next", "give me next"]

    @classmethod
    def plan_task(cls, query: str, session: ConversationState) -> TaskPlan:
        q_lower = query.lower().strip()
        clean_q = re.sub(r"[?!.,]+$", "", q_lower).strip()

        # 1. Context and Available File Detection
        has_tabular = bool(session.files)
        has_documents = bool(session.documents)
        active_dataset = session.active_dataset
        active_doc = session.documents.get(session.active_document_id) if session.active_document_id else (
            list(session.documents.values())[-1] if session.documents else None
        )

        # Disambiguate targeted files by exact/partial name in query
        target_file_id: Optional[str] = None
        target_doc_id: Optional[str] = None
        matched_filename: Optional[str] = None

        # Check tabular filenames by full name, base name
        for fid, fmeta in session.files.items():
            fname_clean = fmeta.file_name.lower()
            base_name = fname_clean.split(".")[0]
            if fname_clean in q_lower or (base_name in q_lower and len(base_name) >= 3):
                target_file_id = fid
                matched_filename = fmeta.file_name
                break

        # Check document filenames
        for did, dmeta in session.documents.items():
            dname_clean = dmeta.file_name.lower()
            base_name = dname_clean.split(".")[0]
            if dname_clean in q_lower or (base_name in q_lower and len(base_name) >= 3) or ("dsa" in q_lower and "dsa" in base_name):
                target_doc_id = did
                matched_filename = dmeta.file_name
                break

        # Fallback to active file/document if not specifically named
        if not target_file_id and active_dataset:
            target_file_id = active_dataset.file_id
        if not target_doc_id and active_doc:
            target_doc_id = active_doc.document_id

        # 2. Conversational Intent Check (Pure greetings, casual chat, thanks)
        is_greeting_or_casual = any(re.search(pat, clean_q) for pat in cls.CONVERSATIONAL_PATTERNS)
        has_tool_indicators = (
            any(w in q_lower for w in [
                "pdf", "csv", "excel", "spreadsheet", "dataset", "paper", "papers",
                "research", "news", "summarize", "table", "row", "rows", "column", "columns",
                "average", "avg", "salary", "revenue", "sales", "search the web", "search the internet",
                "chart", "graph", "plot"
            ])
            or bool(re.search(r"\bpage\s+\d+\b", q_lower))
            or bool(re.search(r"\bchapter\s+\d+\b", q_lower))
        )
        if is_greeting_or_casual and not has_tool_indicators:
            return TaskPlan(
                task_type="direct_answer",
                operation="conversational",
                output_format="text",
                query=query,
                status="valid"
            )

        # 3. Follow-Up / Pagination Detection
        followup_match = cls.FOLLOWUP_COUNT_REGEX.search(q_lower)
        is_generic_followup = any(re.search(p, q_lower) for p in cls.FOLLOWUP_GENERIC_PATTERNS) or q_lower in cls.FOLLOWUP_WORDS

        if followup_match or is_generic_followup:
            req_n = int(followup_match.group(1)) if followup_match else 5
            last_tool = session.last_tool_call

            if last_tool:
                prev_params = last_tool.parameters or {}
                if last_tool.tool_name == "search_data":
                    prev_offset = prev_params.get("offset", 0)
                    prev_n = prev_params.get("n", prev_params.get("top_k", 5))
                    offset = prev_offset + prev_n
                    return TaskPlan(
                        task_type="data_extraction",
                        sources=[TaskSource(type="spreadsheet", file_id=target_file_id, filename=active_dataset.file_name if active_dataset else None)],
                        operation="first_n",
                        requested_count=req_n,
                        offset=offset,
                        ordering="source_order",
                        output_format="table",
                        requires_data=True,
                        query=query,
                        is_follow_up=True,
                        target_file_id=target_file_id,
                        status="valid"
                    )
                elif last_tool.tool_name == "search_documents":
                    prev_offset = prev_params.get("offset", 0)
                    prev_n = prev_params.get("requested_count", 5)
                    offset = prev_offset + prev_n
                    return TaskPlan(
                        task_type="document_extraction",
                        sources=[TaskSource(type="uploaded_pdf", file_id=target_doc_id, filename=active_doc.file_name if active_doc else None)],
                        operation="extract",
                        requested_count=req_n,
                        offset=offset,
                        ordering="document_order",
                        output_format="table",
                        requires_document=True,
                        query=query,
                        is_follow_up=True,
                        target_document_id=target_doc_id,
                        status="valid"
                    )

            # Follow-up requested but context is missing or ambiguous
            return TaskPlan(
                task_type="direct_answer",
                operation="clarification",
                output_format="text",
                query=query,
                is_follow_up=True,
                status="clarification_needed",
                explanation="I am not sure what you would like to see the next items of. Please specify whether you would like to view more records from your dataset or questions/pages from your document."
            )

        # 4. Context & Semantic Signals
        is_uploaded_doc_ref = (
            bool(re.search(r"\b(?:the|this|uploaded|attached|my|that)\s+paper\b", q_lower))
            or bool(re.search(r"\b(?:that|this|the|uploaded|attached)\s+pdf\b", q_lower))
        )
        mentions_pdf = (
            any(w in q_lower for w in [
                "pdf", "uploaded pdf", "attached pdf", "this pdf", "that pdf", "uploaded document",
                "this document", "report", "dsa pdf", "in the pdf", "from the pdf"
            ])
            or is_uploaded_doc_ref
            or ("dsa" in q_lower and any(w in q_lower for w in ["question", "questions", "sheet", "pdf"]))
        )

        mentions_spreadsheet = any(w in q_lower for w in [
            "spreadsheet", "excel", "csv", "sales", "revenue", "row", "rows", "column", "columns",
            "record", "records", "dataset", "table"
        ]) or bool(
            target_file_id and any(w in q_lower for w in ["product", "products", "region", "price", "sales"])
        )

        mentions_research = (
            any(w in q_lower for w in cls.SCHOLARLY_KEYWORDS)
            or bool(re.search(r"\b\d+\s+papers\b", q_lower))
            or any(w in q_lower for w in ["arxiv", "survey", "literature", "recent papers", "latest papers"])
            or (bool(re.search(r"\bpapers\b", q_lower)) and not is_uploaded_doc_ref)
        )

        # 5. Pure Web Search Routing (e.g. "Give me recent AI news", "Search the internet for SQLite PRAGMA commands")
        is_web_search_query = (
            any(w in q_lower for w in cls.WEB_SEARCH_KEYWORDS)
            or bool(re.search(r"\b(?:recent|latest|current|today'?s?|breaking)\s+(?:ai\s+)?news\b", q_lower))
            or bool(re.search(r"\b(?:news|headlines)\s+about\b", q_lower))
            or (any(w in q_lower for w in ["news", "latest updates"]) and not any(w in q_lower for w in ["research paper", "arxiv", "pdf", "spreadsheet", "dataset"]))
        )
        if is_web_search_query:
            return TaskPlan(
                task_type="web_search",
                sources=[TaskSource(type="web")],
                operation="search",
                requires_web=True,
                output_format="text",
                query=query,
                status="valid"
            )

        # 6. Mixed / Hybrid Evaluation
        # Case 1: Spreadsheet + Research (e.g., "Analyze my sales Excel file and find research explaining why revenue changed")
        if (mentions_spreadsheet or has_tabular) and mentions_research and any(w in q_lower for w in ["explain", "why", "trend", "pattern", "consumer", "literature", "theory", "season"]):
            return TaskPlan(
                task_type="mixed",
                sources=[
                    TaskSource(type="spreadsheet", file_id=target_file_id, filename=active_dataset.file_name if active_dataset else None),
                    TaskSource(type="web")
                ],
                operation="analyze_and_research",
                requires_data=True,
                requires_web=True,
                output_format="table",
                query=query,
                target_file_id=target_file_id,
                status="valid"
            )

        # Case 2: Document + Research (e.g., "Read the DSA PDF and find recent research papers about the concepts in it")
        if (mentions_pdf or has_documents) and mentions_research and any(w in q_lower for w in ["in it", "concepts", "read", "literature", "explain", "compare", "discussed"]):
            return TaskPlan(
                task_type="mixed",
                sources=[
                    TaskSource(type="uploaded_pdf", file_id=target_doc_id, filename=active_doc.file_name if active_doc else None),
                    TaskSource(type="web")
                ],
                operation="extract_and_research",
                requires_document=True,
                requires_web=True,
                output_format="research_list",
                query=query,
                target_document_id=target_doc_id,
                status="valid"
            )

        # 7. Pure Scholarly Research Agent Routing
        has_explicit_doc_ref = any(w in q_lower for w in [
            "pdf", "uploaded pdf", "attached pdf", "this pdf", "that pdf", "uploaded document",
            "this document", "the report", "in it", "from the pdf", "in the pdf", "from the document",
            "read the"
        ]) or is_uploaded_doc_ref

        if mentions_research and not has_explicit_doc_ref:
            count_m = re.search(r"\b(\d+)\s*(?:papers|sources|articles)\b", q_lower)
            req_count = int(count_m.group(1)) if count_m else 5
            return TaskPlan(
                task_type="research",
                sources=[TaskSource(type="web")],
                operation="search_and_synthesize",
                requested_count=req_count,
                requires_web=True,
                output_format="research_list",
                query=query,
                status="valid"
            )

        # 8. Document Operations (Page Lookup, Extraction, Search, Missing Document)
        page_m = re.search(r"\bpage\s+(\d+)\b", q_lower)
        if page_m and (mentions_pdf or "page" in q_lower):
            page_num = int(page_m.group(1))
            if not has_documents:
                return TaskPlan(
                    task_type="document_search",
                    operation="page_lookup",
                    target_page=page_num,
                    requires_document=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="document",
                    explanation="No PDF document is currently uploaded in this session. Please upload a PDF file to look up page content."
                )
            return TaskPlan(
                task_type="document_search",
                sources=[TaskSource(type="uploaded_pdf", file_id=target_doc_id, filename=active_doc.file_name if active_doc else None)],
                operation="page_lookup",
                target_page=page_num,
                requires_document=True,
                output_format="document_excerpts",
                query=query,
                target_document_id=target_doc_id,
                status="valid"
            )

        # Range extraction: e.g. "questions 21 to 30", "questions 21-30"
        range_m = re.search(r"(?:questions?|items?)\s*(\d+)\s*(?:to|-)\s*(\d+)", q_lower)
        if not range_m and (mentions_pdf or "question" in q_lower):
            num_range_m = re.search(r"\b(\d+)\s*(?:to|-)\s*(\d+)\b", q_lower)
            if num_range_m:
                s_val, e_val = int(num_range_m.group(1)), int(num_range_m.group(2))
                if e_val >= s_val and (e_val - s_val) <= 50:
                    range_m = num_range_m

        if range_m and (mentions_pdf or "question" in q_lower):
            start_n, end_n = int(range_m.group(1)), int(range_m.group(2))
            count = end_n - start_n + 1
            if not has_documents:
                return TaskPlan(
                    task_type="document_extraction",
                    operation="extract",
                    target_range=[start_n, end_n],
                    requested_count=count,
                    requires_document=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="document",
                    explanation="No PDF document is currently uploaded. Please upload a PDF file to extract questions."
                )
            return TaskPlan(
                task_type="document_extraction",
                sources=[TaskSource(type="uploaded_pdf", file_id=target_doc_id, filename=active_doc.file_name if active_doc else None)],
                operation="extract",
                target_range=[start_n, end_n],
                requested_count=count,
                ordering="document_order",
                requires_document=True,
                output_format="table",
                query=query,
                target_document_id=target_doc_id,
                status="valid"
            )

        # All questions extraction
        all_count_m = re.search(r"(?:all\s+(\d+)|all\s+ten)\b", q_lower)
        if (all_count_m or "all questions" in q_lower or "all 10" in q_lower) and (mentions_pdf or "question" in q_lower or "dsa" in q_lower):
            count = int(all_count_m.group(1)) if (all_count_m and all_count_m.group(1)) else 10
            if not has_documents:
                return TaskPlan(
                    task_type="document_extraction",
                    operation="extract",
                    requested_count=count,
                    requires_document=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="document",
                    explanation="No PDF document is currently uploaded. Please upload a PDF file to extract questions."
                )
            return TaskPlan(
                task_type="document_extraction",
                sources=[TaskSource(type="uploaded_pdf", file_id=target_doc_id, filename=active_doc.file_name if active_doc else None)],
                operation="extract",
                requested_count=count,
                ordering="document_order",
                requires_document=True,
                output_format="table",
                query=query,
                target_document_id=target_doc_id,
                status="valid"
            )

        # First N questions extraction
        first_q_m = re.search(r"(?:first|give me the first)\s+(\d+)\s*(?:questions?|problems?|items?)", q_lower)
        if first_q_m and (mentions_pdf or "question" in q_lower or "dsa" in q_lower):
            count = int(first_q_m.group(1))
            if not has_documents:
                return TaskPlan(
                    task_type="document_extraction",
                    operation="extract",
                    requested_count=count,
                    requires_document=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="document",
                    explanation="No PDF document is currently uploaded. Please upload a PDF file to extract questions."
                )
            return TaskPlan(
                task_type="document_extraction",
                sources=[TaskSource(type="uploaded_pdf", file_id=target_doc_id, filename=active_doc.file_name if active_doc else None)],
                operation="extract",
                requested_count=count,
                offset=0,
                ordering="document_order",
                requires_document=True,
                output_format="table",
                query=query,
                target_document_id=target_doc_id,
                status="valid"
            )

        # Explicit document search / summary
        is_explicit_doc_query = (
            mentions_pdf
            or bool(re.search(r"\b(?:summarize|summary\s+of)\s+(?:my\s+|the\s+)?(?:uploaded\s+)?(?:pdf|document|report|paper)\b", q_lower))
            or bool(re.search(r"\bchapter\s+\d+\b", q_lower))
            or (has_documents and any(w in q_lower for w in ["in the pdf", "from the pdf", "dsa pdf", "that pdf", "this pdf", "the report"]))
        )
        if is_explicit_doc_query:
            if not has_documents:
                return TaskPlan(
                    task_type="document_search",
                    operation="search",
                    requires_document=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="document",
                    explanation="No PDF document is currently uploaded in this session. Please upload a PDF file to proceed."
                )
            return TaskPlan(
                task_type="document_search",
                sources=[TaskSource(type="uploaded_pdf", file_id=target_doc_id, filename=active_doc.file_name if active_doc else None)],
                operation="search",
                requires_document=True,
                output_format="document_excerpts",
                query=query,
                target_document_id=target_doc_id,
                status="valid"
            )

        # 9. Tabular / Spreadsheet Operations
        # Helper to match dataset columns accurately
        def match_dataset_col(raw: str) -> str:
            if not active_dataset:
                return raw
            t = raw.strip().lower()
            for c in active_dataset.columns:
                if c.name.lower() == t:
                    return c.name
            for c in active_dataset.columns:
                cn = c.name.lower()
                if cn.endswith("y") and (cn[:-1] + "ies") == t:
                    return c.name
                if (cn + "s") == t or (cn + "es") == t:
                    return c.name
                if cn.rstrip("s") == t.rstrip("s"):
                    return c.name
            for c in active_dataset.columns:
                if c.name.lower() in t or t in c.name.lower():
                    return c.name
            return raw

        # First N rows
        first_rows_m = re.search(r"(?:first|give me the first)\s+(\d+)\s*(?:rows?|data points?|records?|items?)", q_lower)
        if first_rows_m or "first 5 rows" in q_lower or "first 5 data points" in q_lower:
            count = int(first_rows_m.group(1)) if first_rows_m else 5
            if not has_tabular:
                return TaskPlan(
                    task_type="data_extraction",
                    operation="first_n",
                    requested_count=count,
                    requires_data=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="spreadsheet",
                    explanation="No dataset (CSV or Excel) is currently uploaded in this session. Please upload a dataset to view rows."
                )
            return TaskPlan(
                task_type="data_extraction",
                sources=[TaskSource(type="spreadsheet", file_id=target_file_id, filename=active_dataset.file_name if active_dataset else None)],
                operation="first_n",
                requested_count=count,
                offset=0,
                ordering="source_order",
                requires_data=True,
                output_format="table",
                query=query,
                target_file_id=target_file_id,
                status="valid"
            )

        # "top 5 products by revenue"
        top_by_m = re.search(r"top\s+(\d+)\s+([a-zA-Z0-9_\s]+?)\s+by\s+([a-zA-Z0-9_\s]+)", q_lower)
        if top_by_m:
            count = int(top_by_m.group(1))
            grp_entity = top_by_m.group(2).strip()
            metric_col = top_by_m.group(3).strip()
            if not has_tabular:
                return TaskPlan(
                    task_type="data_analysis",
                    operation="top_n",
                    requested_count=count,
                    requires_data=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="spreadsheet",
                    explanation="No dataset (CSV or Excel) is currently uploaded in this session. Please upload a dataset to compute rankings."
                )
            resolved_grp = match_dataset_col(grp_entity)
            resolved_metric = match_dataset_col(metric_col)
            return TaskPlan(
                task_type="data_analysis",
                sources=[TaskSource(type="spreadsheet", file_id=target_file_id, filename=active_dataset.file_name if active_dataset else None)],
                operation="top_n",
                requested_count=count,
                group_by_column=resolved_grp,
                metric_column=resolved_metric,
                sort_column=resolved_metric,
                ordering="metric_desc",
                requires_data=True,
                output_format="table",
                query=query,
                target_file_id=target_file_id,
                status="valid"
            )

        # Filter: "where region is East"
        filter_m = re.search(r"where\s+([a-zA-Z0-9_]+)\s*(?:is|=|equals)\s*([a-zA-Z0-9_\s]+)", q_lower)
        if filter_m and (has_tabular or mentions_spreadsheet):
            f_col = filter_m.group(1).strip()
            f_val = filter_m.group(2).strip()
            if not has_tabular:
                return TaskPlan(
                    task_type="data_extraction",
                    operation="filter",
                    requires_data=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="spreadsheet",
                    explanation="No dataset is uploaded to filter. Please upload a dataset to proceed."
                )
            return TaskPlan(
                task_type="data_extraction",
                sources=[TaskSource(type="spreadsheet", file_id=target_file_id, filename=active_dataset.file_name if active_dataset else None)],
                operation="filter",
                filter_criteria={f_col: f_val},
                requires_data=True,
                output_format="table",
                query=query,
                target_file_id=target_file_id,
                status="valid"
            )

        # Aggregation with group: "average revenue by region"
        agg_m = re.search(r"(?:calculate\s+)?(average|avg|sum|count|max|min)\s+([a-zA-Z0-9_\s]+?)\s+by\s+([a-zA-Z0-9_\s]+)", q_lower)
        if agg_m:
            func = agg_m.group(1).upper()
            m_col = agg_m.group(2).strip()
            g_col = agg_m.group(3).strip()
            if not has_tabular:
                return TaskPlan(
                    task_type="data_analysis",
                    operation="aggregate",
                    requires_data=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="spreadsheet",
                    explanation="No dataset (CSV or Excel) is currently uploaded in this session. Please upload a dataset to calculate aggregates."
                )
            return TaskPlan(
                task_type="data_analysis",
                sources=[TaskSource(type="spreadsheet", file_id=target_file_id, filename=active_dataset.file_name if active_dataset else None)],
                operation="aggregate",
                group_by_column=match_dataset_col(g_col),
                metric_column=match_dataset_col(m_col),
                requires_data=True,
                output_format="table",
                query=query,
                target_file_id=target_file_id,
                status="valid"
            )

        # Single metric aggregation without 'by': "calculate average salary", "find the average salary", "average revenue"
        single_agg_m = re.search(r"(?:calculate|find|what\s+is\s+the)?\s*(?:the\s+)?(average|avg|sum|total|count|maximum|max|minimum|min)\s+(?:of\s+)?([a-zA-Z0-9_]+)", q_lower)
        if single_agg_m and any(w in q_lower for w in ["salary", "revenue", "sales", "price", "profit", "cost", "quantity", "data", "spreadsheet"]):
            func = single_agg_m.group(1).upper()
            m_col = single_agg_m.group(2).strip()
            if not has_tabular:
                return TaskPlan(
                    task_type="data_analysis",
                    operation="aggregate",
                    metric_column=m_col,
                    requires_data=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="spreadsheet",
                    explanation="No dataset (CSV or Excel) is currently uploaded in this session. Please upload a dataset to calculate this metric."
                )
            return TaskPlan(
                task_type="data_analysis",
                sources=[TaskSource(type="spreadsheet", file_id=target_file_id, filename=active_dataset.file_name if active_dataset else None)],
                operation="aggregate",
                metric_column=match_dataset_col(m_col),
                requires_data=True,
                output_format="table",
                query=query,
                target_file_id=target_file_id,
                status="valid"
            )

        # Visualization
        if any(w in q_lower for w in ["chart", "plot", "graph", "visualize", "visualization"]):
            if not has_tabular:
                return TaskPlan(
                    task_type="visualization",
                    operation="visualize",
                    requires_data=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="spreadsheet",
                    explanation="No dataset is currently uploaded. Please upload a dataset to generate charts."
                )
            return TaskPlan(
                task_type="visualization",
                sources=[TaskSource(type="spreadsheet", file_id=target_file_id, filename=active_dataset.file_name if active_dataset else None)],
                operation="visualize",
                requires_data=True,
                output_format="chart",
                query=query,
                target_file_id=target_file_id,
                status="valid"
            )

        # Schema inspection
        if any(w in q_lower for w in ["schema", "what columns", "show columns", "list columns"]):
            if not has_tabular:
                return TaskPlan(
                    task_type="schema_inspection",
                    operation="inspect_schema",
                    requires_data=True,
                    query=query,
                    status="missing_resource",
                    missing_resource="spreadsheet",
                    explanation="No dataset is currently uploaded. Please upload a dataset to inspect its schema."
                )
            return TaskPlan(
                task_type="schema_inspection",
                sources=[TaskSource(type="spreadsheet", file_id=target_file_id, filename=active_dataset.file_name if active_dataset else None)],
                operation="inspect_schema",
                requires_data=True,
                output_format="text",
                query=query,
                target_file_id=target_file_id,
                status="valid"
            )

        # Search Data Records explicitly
        if mentions_spreadsheet or (target_file_id and any(w in q_lower for w in ["records", "items", "find any records"])):
            return TaskPlan(
                task_type="data_extraction",
                sources=[TaskSource(type="spreadsheet", file_id=target_file_id, filename=active_dataset.file_name if active_dataset else None)],
                operation="search",
                requires_data=True,
                output_format="table",
                query=query,
                target_file_id=target_file_id,
                status="valid"
            )

        # 10. Direct Answer Fallback for General Knowledge & Questions
        # NEVER assume document or dataset retrieval simply because files exist
        return TaskPlan(
            task_type="direct_answer",
            operation="direct_answer",
            output_format="text",
            query=query,
            status="valid"
        )


task_planner = TaskPlanner()
