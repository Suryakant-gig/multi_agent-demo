from typing import Dict, Any, List, Optional
from app.tools.base import BaseTool
from app.retrieval.document_retriever import document_retriever
from app.utils.logger import logger


class SearchDocumentsTool(BaseTool):
    """
    Retrieves relevant passages and excerpts from uploaded PDF documents.
    Supports specific page lookups and semantic keyword retrieval.
    Provides verifiable citations with file name and page numbers.
    """
    name = "search_documents"
    description = (
        "Search uploaded PDF documents for relevant text, methodology, sections, or specific pages. "
        "Use this tool when the user asks questions about uploaded papers, reports, or PDF documents."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language search query or page request (e.g. 'methodology section', 'page 10')."
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
            "chunk_count": {"type": "integer"},
            "results": {"type": "array"},
            "citations": {"type": "array"}
        }
    }
    usage_example = {
        "query": "What is the evaluation benchmark used in the paper?",
        "top_k": 3
    }

    def execute(self, session_id: str, **kwargs) -> Dict[str, Any]:
        query = kwargs.get("query", "")
        top_k = kwargs.get("top_k", 4)
        document_id = kwargs.get("document_id")

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

        return {
            "query": query,
            "chunk_count": len(results),
            "results": results,
            "citations": citations
        }
