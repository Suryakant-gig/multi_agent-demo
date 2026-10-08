import re
from typing import List, Dict, Any


class WebRanker:
    """
    Ranks web and academic search results according to semantic relevance,
    source authority (scholarly papers and official docs prioritized), and recency.
    Deduplicates URLs and limits candidates.
    """

    AUTHORITY_DOMAIN_BOOSTS = {
        "arxiv.org": 0.25,
        "semanticscholar.org": 0.25,
        "acm.org": 0.25,
        "ieee.org": 0.25,
        "nature.com": 0.25,
        "openreview.net": 0.22,
        "paperswithcode.com": 0.20,
        "sqlite.org": 0.20,
        "fastapi.tiangolo.com": 0.20,
        "python.org": 0.20,
        "github.com": 0.15,
        "readthedocs.io": 0.15,
        "w3.org": 0.15
    }

    SOURCE_TYPE_BOOSTS = {
        "paper": 0.20,
        "documentation": 0.18,
        "article": 0.08,
        "website": 0.00
    }

    def rank_candidates(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 5,
        prefer_research: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Deduplicates, scores, and sorts candidates to select the top_k authoritative sources.
        """
        seen_urls = set()
        unique_candidates = []

        for c in candidates:
            url = c.get("url", "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            unique_candidates.append(c)

        q_tokens = re.findall(r"\b\w{3,}\b", query.lower())

        scored_candidates = []
        for item in unique_candidates:
            base_score = float(item.get("relevance_score", 0.70))
            domain = item.get("domain", "").lower()
            source_type = item.get("source_type", "website")
            title = item.get("title", "").lower()
            snippet = item.get("snippet", "").lower()

            # 1. Authority boost
            auth_boost = 0.0
            for auth_domain, boost in self.AUTHORITY_DOMAIN_BOOSTS.items():
                if auth_domain in domain:
                    auth_boost = boost
                    break

            # 2. Source type boost
            type_boost = self.SOURCE_TYPE_BOOSTS.get(source_type, 0.0) if prefer_research else 0.0

            # 3. Query match boost in title
            title_matches = sum(1 for t in q_tokens if t in title)
            title_boost = min(title_matches * 0.05, 0.15)

            # Combined score
            final_score = round(min(base_score + auth_boost + type_boost + title_boost, 0.99), 3)
            item_copy = dict(item)
            item_copy["relevance_score"] = final_score
            scored_candidates.append(item_copy)

        scored_candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored_candidates[:top_k]


web_ranker = WebRanker()
