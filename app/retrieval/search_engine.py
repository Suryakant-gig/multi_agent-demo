from typing import List, Dict, Any, Optional
from app.models.domain import DatasetMetadata, SearchResultItem
from app.services.storage_engine import storage_engine
from app.retrieval.ranker import RelevanceRanker
from app.utils.logger import logger


class SearchEngine:
    """
    Search retrieval engine that handles:
    - Query understanding & keyword extraction
    - Filter parsing
    - Candidate retrieval from storage
    - Scoring, ranking, and deduplication
    - Source citation attachment
    """

    def search(
        self,
        session_id: str,
        dataset: DatasetMetadata,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5
    ) -> List[SearchResultItem]:
        tokens = RelevanceRanker.tokenize(query)
        col_names = [c.name for c in dataset.columns]
        
        # Candidate retrieval: pull matching rows from storage engine
        # Over-fetch candidate pool (e.g., top_k * 4) to allow ranker to select best Top-K
        candidate_limit = max(top_k * 4, 20)
        
        candidates = storage_engine.search_records(
            session_id=session_id,
            table_name=dataset.db_table_name,
            search_terms=tokens if tokens else [query],
            columns=col_names,
            top_k=candidate_limit
        )

        # Apply optional explicit key-value filters
        if filters:
            filtered_candidates = []
            for row in candidates:
                match = True
                for f_col, f_val in filters.items():
                    if f_col in row and str(row[f_col]).lower() != str(f_val).lower():
                        match = False
                        break
                if match:
                    filtered_candidates.append(row)
            candidates = filtered_candidates

        # Rank and return top_k
        ranked_results = RelevanceRanker.rank_and_deduplicate(
            candidates=candidates,
            query=query,
            file_id=dataset.file_id,
            file_name=dataset.file_name,
            top_k=top_k
        )

        return ranked_results


search_engine = SearchEngine()
