import re
from typing import List, Dict, Any, Tuple
from app.models.domain import SearchResultItem
from app.retrieval.citation import CitationGenerator


class RelevanceRanker:
    """
    Ranks candidate records using token matching, exact phrase matches,
    and field relevance weighting. Deduplicates identical records.
    """

    @staticmethod
    def tokenize(text: str) -> List[str]:
        return [t.lower() for t in re.findall(r"\w+", text) if len(t) > 1]

    @classmethod
    def calculate_score(cls, record: Dict[str, Any], query_tokens: List[str], raw_query: str) -> Tuple[float, List[str]]:
        if not query_tokens:
            return 1.0, []

        score = 0.0
        matched_columns = []
        raw_query_lower = raw_query.lower()

        for col, val in record.items():
            if col.startswith("_"):
                continue
            val_str = str(val).lower() if val is not None else ""
            if not val_str:
                continue

            # Exact full phrase match in field
            if raw_query_lower in val_str:
                score += 3.0
                if col not in matched_columns:
                    matched_columns.append(col)

            # Token level matches
            for token in query_tokens:
                if token in val_str:
                    score += 1.0
                    if col not in matched_columns:
                        matched_columns.append(col)
                    # Extra boost if token is exact match with full value
                    if token == val_str:
                        score += 1.5

        return score, matched_columns

    @classmethod
    def rank_and_deduplicate(
        cls,
        candidates: List[Dict[str, Any]],
        query: str,
        file_id: str,
        file_name: str,
        top_k: int = 5
    ) -> List[SearchResultItem]:
        query_tokens = cls.tokenize(query)
        scored_items: List[SearchResultItem] = []
        seen_fingerprints = set()

        for cand in candidates:
            row_id = cand.get("_row_id")
            # Build fingerprint for deduplication (excluding internal _row_id)
            fingerprint = tuple(sorted((k, str(v)) for k, v in cand.items() if not k.startswith("_")))
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)

            score, matched_cols = cls.calculate_score(cand, query_tokens, query)
            citation = CitationGenerator.create_citation(
                file_id=file_id,
                file_name=file_name,
                row_index=row_id,
                matched_columns=matched_cols,
                data_record=cand
            )

            scored_items.append(
                SearchResultItem(
                    row_index=row_id or 0,
                    score=round(score, 2),
                    data={k: v for k, v in cand.items() if not k.startswith("_")},
                    citation=citation
                )
            )

        # Sort descending by score
        scored_items.sort(key=lambda x: x.score, reverse=True)
        return scored_items[:top_k]
