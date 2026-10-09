from typing import Dict, Any, List, Optional
from app.tools.base import BaseTool
from app.retrieval.document_retriever import document_retriever
from app.state.session_manager import session_manager
from app.utils.logger import logger


class SearchDocumentsTool(BaseTool):
    """
    Retrieves or deterministically extracts passages, numbered questions, and tables from uploaded PDF documents.
    Supports specific page lookups, sequential extraction (first N, next N, range N to M), and semantic keyword retrieval.
    Provides verifiable citations with file name and exact page numbers.
    """
    name = "search_documents"
    description = (
        "Search or extract text, methodology, sections, questions, or specific pages from uploaded PDF documents. "
        "Use this tool when the user asks questions about uploaded papers, reports, or PDF documents. "
        "Supports 'extract' operation for deterministic question/item lists and 'search' for semantic queries."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query, question request, or page request (e.g. 'first 5 questions', 'questions 21 to 30', 'page 10')."
            },
            "operation": {
                "type": "string",
                "enum": ["search", "extract"],
                "description": "Operation type: 'extract' for deterministic question/list extraction, 'search' for semantic passages.",
                "default": "search"
            },
            "requested_count": {
                "type": "integer",
                "description": "Number of items or questions to extract (for extraction operations)."
            },
            "offset": {
                "type": "integer",
                "description": "Item offset for pagination or 'next N' questions (default: 0).",
                "default": 0
            },
            "target_range": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Optional question number range, e.g. [21, 30] for questions 21 to 30."
            },
            "top_k": {
                "type": "integer",
                "description": "Number of top matching chunks to retrieve (default: 4).",
                "default": 4
            },
            "document_id": {
                "type": "string",
                "description": "Optional specific document ID to restrict search."
            }
        },
        "required": ["query"]
    }
    output_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "operation": {"type": "string"},
            "chunk_count": {"type": "integer"},
            "requested_count": {"type": "integer"},
            "extracted_count": {"type": "integer"},
            "is_complete": {"type": "boolean"},
            "items": {"type": "array"},
            "table": {"type": "object"},
            "results": {"type": "array"},
            "citations": {"type": "array"}
        }
    }
    usage_example = {
        "query": "Give me the first 5 questions from the PDF",
        "operation": "extract",
        "requested_count": 5
    }

    def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "")
        operation = kwargs.get("operation", "search")
        requested_count = kwargs.get("requested_count")
        offset = kwargs.get("offset", 0)
        target_range = kwargs.get("target_range")
        top_k = kwargs.get("top_k", 4)
        document_id = kwargs.get("document_id")

        # Automatically detect if query is an extraction query
        t_range, t_count, is_ext = document_retriever.extract_range_and_count(query)
        if operation == "extract" or is_ext or target_range or (t_count and t_count >= 5):
            effective_range = tuple(target_range) if target_range else t_range
            effective_count = requested_count if requested_count is not None else t_count

            ext_res = document_retriever.extract_document_content(
                session_id=session_id,
                query=query,
                requested_count=effective_count,
                offset=offset,
                target_range=effective_range,
                document_id=document_id
            )

            if document_id:
                session = session_manager.get_session(session_id)
                session.active_document_id = document_id
            elif ext_res.get("items"):
                first_did = ext_res["items"][0].get("document_id")
                if first_did:
                    session = session_manager.get_session(session_id)
                    session.active_document_id = first_did

            citations_dicts = [c.model_dump() for c in ext_res["citations"]]
            return {
                "query": query,
                "operation": "extract",
                "chunk_count": len(ext_res["results"]),
                "requested_count": ext_res["requested_count"],
                "extracted_count": ext_res["extracted_count"],
                "is_complete": ext_res["is_complete"],
                "items": ext_res["items"],
                "table": ext_res["table"],
                "results": ext_res["results"],
                "citations": citations_dicts
            }

        # Otherwise perform standard / semantic search
        items = document_retriever.search_documents(
            session_id=session_id,
            query=query,
            top_k=top_k,
            document_id=document_id
        )

        results = []
        citations = []
        for item in items:
            chunk = item["chunk"]
            citation = item["citation"]
            results.append({
                "document_id": chunk.document_id,
                "file_name": chunk.file_name,
                "page_number": chunk.page_number,
                "text": chunk.text,
                "score": item["score"]
            })
            citations.append(citation.model_dump())

        if document_id:
            session = session_manager.get_session(session_id)
            session.active_document_id = document_id
        elif results:
            session = session_manager.get_session(session_id)
            session.active_document_id = results[0]["document_id"]

        return {
            "query": query,
            "operation": "search",
            "chunk_count": len(results),
            "results": results,
            "citations": citations
        }
