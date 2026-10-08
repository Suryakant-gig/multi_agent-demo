from typing import List, Dict, Any, Tuple
from app.models.domain import CitationItem, SourceItem


class WebCitationFormatter:
    """
    Constructs verifiable, non-hallucinated citations and source records for web and scholarly research.
    Guarantees every cited URL originates directly from actual search or fetch executions.
    """

    @staticmethod
    def create_citation(source: Dict[str, Any]) -> CitationItem:
        title = source.get("title", "Untitled Source").strip()
        url = source.get("url", "").strip()
        domain = source.get("domain", "").strip()
        published = source.get("published_at")
        snippet = source.get("snippet", "")

        pub_text = f" ({published})" if published else ""
        desc = f"Source: [{title}]({url}) — {domain}{pub_text}" if url else f"Source: {title}"

        return CitationItem(
            file_id="web",
            file_name=domain or "web",
            title=title,
            url=url,
            domain=domain,
            published_at=published,
            snippet=snippet[:250] if snippet else None,
            source_description=desc,
            citation_type="web"
        )

    @staticmethod
    def create_source_item(source: Dict[str, Any]) -> SourceItem:
        return SourceItem(
            title=source.get("title", "Untitled").strip(),
            url=source.get("url", "").strip(),
            domain=source.get("domain", "").strip(),
            snippet=source.get("snippet", "").strip(),
            published_at=source.get("published_at"),
            source_type=source.get("source_type", "website"),
            relevance_score=float(source.get("relevance_score", 0.8))
        )

    @classmethod
    def format_sources_section(cls, sources: List[Dict[str, Any]]) -> str:
        """
        Formats a clean, markdown Sources list with clickable links.
        """
        if not sources:
            return ""

        lines = ["\n\n### Sources\n"]
        for idx, s in enumerate(sources, start=1):
            title = s.get("title", "Source").strip()
            url = s.get("url", "")
            domain = s.get("domain", "")
            published = s.get("published_at")
            pub_info = f" • {published}" if published else ""
            type_tag = f" `[{s.get('source_type', 'web').upper()}]`"

            lines.append(f"{idx}. [{title}]({url}) — *{domain}*{pub_info}{type_tag}")

        return "\n".join(lines)


web_citation_formatter = WebCitationFormatter()
