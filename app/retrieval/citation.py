from typing import Dict, Any, List, Optional
from app.models.domain import CitationItem


class CitationGenerator:
    """
    Generates verifiable citations and data sources for retrieved information.
    """

    @staticmethod
    def create_citation(
        file_id: str,
        file_name: str,
        row_index: Optional[int],
        matched_columns: List[str],
        data_record: Dict[str, Any]
    ) -> CitationItem:
        # Build brief informative snippet
        clean_items = [f"{k}: {v}" for k, v in data_record.items() if not k.startswith("_") and v is not None]
        snippet = " | ".join(clean_items[:4])
        if len(clean_items) > 4:
            snippet += f" (+{len(clean_items) - 4} more fields)"

        row_str = f"Row {row_index}" if row_index is not None else "Aggregated Summary"
        desc = f"Source: {file_name} ({row_str})"

        return CitationItem(
            file_id=file_id,
            file_name=file_name,
            row_index=row_index,
            column_names=matched_columns,
            snippet=snippet,
            source_description=desc
        )
