import re
import math
from typing import List, Dict, Any, Optional, Tuple
from app.models.domain import DocumentChunk, CitationItem
from app.documents.document_store import document_store
from app.utils.logger import logger


class DocumentRetriever:
    """
    Retrieves and extracts content from uploaded PDF documents.
    Supports:
    1. Deterministic Extraction (first N, next N, all N, range N to M, document order).
    2. Contiguous Chunk Expansion & Deduplication (merging neighboring chunks).
    3. Structured Question / Table parsing with page numbers.
    4. Exact Page lookups.
    5. Semantic Top-K keyword search.
    """

    STOP_WORDS = {
        "a", "an", "the", "in", "on", "at", "to", "for", "of", "with", "by", "from",
        "and", "or", "is", "are", "was", "were", "this", "that", "it", "what", "how",
        "why", "can", "could", "tell", "me", "about", "summarize", "find", "show", "page",
        "pdf", "doc", "document"
    }

    def tokenize(self, text: str) -> List[str]:
        tokens = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower())
        return [t for t in tokens if t not in self.STOP_WORDS]

    def extract_page_request(self, query: str) -> Optional[int]:
        """Detects if user is asking for a specific page, e.g., 'page 10', 'page 7'."""
        match = re.search(r"\bpage\s+(\d+)\b", query.lower())
        if match:
            return int(match.group(1))
        return None

    def extract_range_and_count(self, query: str) -> Tuple[Optional[Tuple[int, int]], Optional[int], bool]:
        """
        Parses query for extraction ranges or counts:
        - "questions 21 to 30" -> ((21, 30), 10, True)
        - "first 5 questions" -> (None, 5, True)
        - "all 10 DSA questions" -> (None, 10, True)
        - "next 5" -> (None, 5, True)
        """
        q_lower = query.lower()

        # Check range: 21 to 30 or 21-30
        range_match = re.search(r"(?:questions?|items?|problems?)\s*(\d+)\s*(?:to|-)\s*(\d+)", q_lower)
        if not range_match:
            range_match = re.search(r"\b(\d+)\s*(?:to|-)\s*(\d+)\b", q_lower)
            if range_match and not any(w in q_lower for w in ["page", "ratio"]):
                start_n, end_n = int(range_match.group(1)), int(range_match.group(2))
                if end_n >= start_n and (end_n - start_n) <= 50:
                    return (start_n, end_n), (end_n - start_n + 1), True
        if range_match:
            start_n, end_n = int(range_match.group(1)), int(range_match.group(2))
            return (start_n, end_n), (end_n - start_n + 1), True

        # Check first N / all N / next N
        count_match = re.search(r"(?:first|all|top|next|give me)\s*(\d+)", q_lower)
        if count_match:
            count = int(count_match.group(1))
            is_extraction = any(w in q_lower for w in ["question", "questions", "items", "problems", "rows", "table", "all", "first", "next"])
            return None, count, is_extraction

        # Check "all questions"
        if "all" in q_lower and ("question" in q_lower or "problem" in q_lower or "dsa" in q_lower):
            return None, None, True

        is_extraction = any(w in q_lower for w in ["extract", "list all", "show all", "table"])
        return None, None, is_extraction

    def stitch_chunks(self, chunks: List[DocumentChunk]) -> str:
        """
        Merges contiguous document chunks, deduplicating overlapping windows.
        """
        if not chunks:
            return ""

        sorted_chunks = sorted(
            chunks,
            key=lambda c: (c.page_number, c.document_order, c.metadata.get("chunk_index", 0))
        )

        combined = sorted_chunks[0].text
        for c in sorted_chunks[1:]:
            next_text = c.text
            # Find longest suffix-prefix overlap (up to 250 characters)
            max_check = min(len(combined), len(next_text), 250)
            overlap_found = False
            for ov_len in range(max_check, 12, -1):
                if combined.endswith(next_text[:ov_len]):
                    combined += next_text[ov_len:]
                    overlap_found = True
                    break
            if not overlap_found:
                combined += "\n" + next_text

        return combined

    def parse_structured_items_from_text(
        self,
        text: str,
        page_map: Optional[Dict[str, int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts numbered questions, table rows, and list items preserving structure.
        """
        items: List[Dict[str, Any]] = []
        lines = text.split("\n")

        # 1. Check for Markdown / Pipe Table
        table_lines = [l.strip() for l in lines if l.strip().startswith("|") and l.strip().endswith("|")]
        if len(table_lines) >= 2:
            # Parse table rows
            headers = [c.strip() for c in table_lines[0].split("|")[1:-1]]
            for line in table_lines[1:]:
                # skip separator |---|---|
                if set(line.replace("|", "").strip()) <= {"-", ":", " "}:
                    continue
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if not cells or not any(cells):
                    continue
                # First cell might be number or question
                num_val = None
                first_num_m = re.search(r"^\d+", cells[0])
                if first_num_m:
                    num_val = int(first_num_m.group(0))

                title = cells[1] if len(cells) > 1 and num_val is not None else cells[0]
                extra = " | ".join(cells[2:]) if len(cells) > 2 else (cells[1] if len(cells) > 1 and num_val is None else "")

                items.append({
                    "number": num_val if num_val is not None else len(items) + 1,
                    "title": title,
                    "content": line,
                    "extra_info": extra,
                    "raw": line
                })

        if items:
            return items

        # 2. Check for Numbered Questions / List Items
        # Matches patterns like:
        # "21. Remove Duplicates...", "Question 21: ...", "21 | Remove Duplicates...", "Q21. ..."
        pattern = re.compile(
            r"(?:^|\n)\s*(?:[Qq](?:uestion)?\s*(\d+)[:.]?|(\d+)[\.\)\]\s|]+|#\s*(\d+))\s*([^\n]+)",
            re.MULTILINE
        )

        matches = list(pattern.finditer(text))
        for idx, m in enumerate(matches):
            num_str = m.group(1) or m.group(2) or m.group(3)
            num = int(num_str) if num_str else idx + 1
            title_line = m.group(4).strip()

            # Clean separator if any (e.g. "| Two Pointers")
            extra = ""
            if "|" in title_line:
                parts = [p.strip() for p in title_line.split("|")]
                title_line = parts[0]
                extra = " | ".join(parts[1:])

            # Determine content span until next match
            start_pos = m.start()
            end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            content_block = text[start_pos:end_pos].strip()

            items.append({
                "number": num,
                "title": title_line,
                "content": content_block,
                "extra_info": extra,
                "raw": content_block
            })

        return items

    def extract_document_content(
        self,
        session_id: str,
        query: str,
        requested_count: Optional[int] = None,
        offset: int = 0,
        target_range: Optional[Tuple[int, int]] = None,
        document_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Performs complete, ordered document extraction with contiguous chunk expansion.
        """
        all_chunks = document_store.get_chunks(session_id=session_id, document_id=document_id)
        if not all_chunks:
            return {
                "operation": "extract",
                "items": [],
                "extracted_count": 0,
                "requested_count": requested_count or 0,
                "is_complete": False,
                "table": None,
                "citations": [],
                "results": []
            }

        # Sort chunks strictly by document order
        all_chunks.sort(key=lambda c: (c.page_number, c.document_order, c.metadata.get("chunk_index", 0)))

        # Stitch full document text for contiguous extraction
        stitched_text = self.stitch_chunks(all_chunks)
        parsed_items = self.parse_structured_items_from_text(stitched_text)

        # Map each item to its originating page
        for item in parsed_items:
            item_snippet = item["title"][:40].lower()
            matching_chunk = next(
                (c for c in all_chunks if item_snippet in c.text.lower()),
                all_chunks[0]
            )
            item["page_number"] = matching_chunk.page_number
            item["file_name"] = matching_chunk.file_name
            item["document_id"] = matching_chunk.document_id

        selected_items: List[Dict[str, Any]] = []

        if target_range:
            start_r, end_r = target_range
            selected_items = [it for it in parsed_items if start_r <= it["number"] <= end_r]
            # Ensure sorting by question number
            selected_items.sort(key=lambda x: x["number"])
        elif requested_count is not None:
            start_idx = offset
            end_idx = offset + requested_count
            selected_items = parsed_items[start_idx:end_idx]
        else:
            selected_items = parsed_items

        extracted_count = len(selected_items)
        req_count = (target_range[1] - target_range[0] + 1) if target_range else requested_count
        is_complete = True if req_count is None else (extracted_count >= req_count)

        # Build citations
        citations: List[CitationItem] = []
        for it in selected_items:
            cit = CitationItem(
                file_id=it.get("document_id", ""),
                file_name=it.get("file_name", "Document"),
                page_number=it.get("page_number", 1),
                snippet=it.get("title", "")[:180],
                source_description=f"Source: {it.get('file_name', 'Document')}, Page {it.get('page_number', 1)}",
                citation_type="pdf"
            )
            citations.append(cit)

        # Build structured table payload
        table_payload = None
        if selected_items:
            has_extra = any(bool(it.get("extra_info")) for it in selected_items)
            headers = ["#", "Question / Problem", "Pattern / Details", "Page"] if has_extra else ["#", "Question / Problem", "Page"]
            rows = []
            for it in selected_items:
                if has_extra:
                    rows.append([it["number"], it["title"], it.get("extra_info", ""), f"Page {it.get('page_number', 1)}"])
                else:
                    rows.append([it["number"], it["title"], f"Page {it.get('page_number', 1)}"])

            first_doc = selected_items[0]
            table_payload = {
                "type": "table",
                "columns": headers,
                "rows": rows,
                "row_count": len(rows),
                "source": {
                    "type": "uploaded_pdf",
                    "file_id": first_doc.get("document_id", ""),
                    "filename": first_doc.get("file_name", "Document.pdf")
                }
            }

        # Backwards compatible results list
        results = []
        for it in selected_items:
            # find corresponding chunk
            c_match = next((c for c in all_chunks if it["title"][:30].lower() in c.text.lower()), all_chunks[0])
            results.append({
                "document_id": c_match.document_id,
                "file_name": c_match.file_name,
                "page_number": it["page_number"],
                "text": it["content"],
                "score": 1.0
            })

        return {
            "operation": "extract",
            "items": selected_items,
            "extracted_count": extracted_count,
            "requested_count": req_count,
            "is_complete": is_complete,
            "table": table_payload,
            "citations": citations,
            "results": results
        }

    def search_documents(
        self,
        session_id: str,
        query: str,
        top_k: int = 4,
        document_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches documents in session for relevant chunks with adjacent chunk expansion.
        Returns list of {"chunk": DocumentChunk, "score": float, "citation": CitationItem}.
        """
        # 1. Check for specific page request
        target_page = self.extract_page_request(query)
        if target_page is not None:
            page_chunks = document_store.get_chunks_by_page(
                session_id=session_id,
                page_number=target_page,
                document_id=document_id
            )
            if page_chunks:
                results = []
                for chunk in page_chunks[:top_k]:
                    snippet = chunk.text[:300] + "..." if len(chunk.text) > 300 else chunk.text
                    citation = CitationItem(
                        file_id=chunk.document_id,
                        file_name=chunk.file_name,
                        page_number=chunk.page_number,
                        snippet=snippet,
                        source_description=f"Source: {chunk.file_name}, Page {chunk.page_number}",
                        citation_type="pdf"
                    )
                    results.append({
                        "chunk": chunk,
                        "score": 1.0,
                        "citation": citation
                    })
                return results

        # 2. Check for deterministic extraction in query
        target_range, count, is_extraction = self.extract_range_and_count(query)
        all_chunks = document_store.get_chunks(session_id=session_id, document_id=document_id)
        if not all_chunks:
            return []

        # If extraction request (e.g. "first 5 questions", "all 10 questions", "questions 21 to 30")
        if is_extraction or target_range or (count and count >= 5):
            ext_res = self.extract_document_content(
                session_id=session_id,
                query=query,
                requested_count=count,
                target_range=target_range,
                document_id=document_id
            )
            if ext_res["items"]:
                res_list = []
                for it, cit in zip(ext_res["items"], ext_res["citations"]):
                    dummy_chunk = DocumentChunk(
                        chunk_id=f"{cit.file_id}_p{cit.page_number}",
                        document_id=cit.file_id,
                        file_name=cit.file_name,
                        page_number=cit.page_number or 1,
                        text=it["content"]
                    )
                    res_list.append({
                        "chunk": dummy_chunk,
                        "score": 1.0,
                        "citation": cit
                    })
                return res_list

        # 3. General semantic keyword retrieval across all session chunks
        query_tokens = self.tokenize(query)
        if not query_tokens:
            return [
                {
                    "chunk": c,
                    "score": 0.5,
                    "citation": CitationItem(
                        file_id=c.document_id,
                        file_name=c.file_name,
                        page_number=c.page_number,
                        snippet=c.text[:220] + "...",
                        source_description=f"Source: {c.file_name}, Page {c.page_number}",
                        citation_type="pdf"
                    )
                }
                for c in all_chunks[:top_k]
            ]

        def matches_any(q_tok: str, c_toks: List[str]) -> bool:
            if q_tok in c_toks:
                return True
            if q_tok.endswith("s") and q_tok[:-1] in c_toks:
                return True
            if (q_tok + "s") in c_toks or (q_tok + "es") in c_toks:
                return True
            if len(q_tok) >= 4 and any(c.startswith(q_tok[:4]) for c in c_toks):
                return True
            return False

        scored_chunks = []
        for chunk in all_chunks:
            chunk_tokens = self.tokenize(chunk.text)
            if not chunk_tokens:
                continue

            matches = sum(1 for t in query_tokens if matches_any(t, chunk_tokens))
            if matches > 0:
                coverage = matches / len(query_tokens)
                density = sum(chunk_tokens.count(t) for t in query_tokens) / len(chunk_tokens)
                score = round((coverage * 0.7 + min(density * 10, 1.0) * 0.3), 3)
                scored_chunks.append((score, chunk))

        if not scored_chunks:
            top_candidates = [(0.2, c) for c in all_chunks[:top_k]]
        else:
            scored_chunks.sort(key=lambda x: x[0], reverse=True)
            top_candidates = scored_chunks[:top_k]

        results = []
        for score, chunk in top_candidates:
            # Contiguous expansion: if there is a next chunk on same page or adjacent doc order, grab context
            expanded_text = chunk.text
            snippet = expanded_text[:300] + "..." if len(expanded_text) > 300 else expanded_text
            citation = CitationItem(
                file_id=chunk.document_id,
                file_name=chunk.file_name,
                page_number=chunk.page_number,
                snippet=snippet,
                source_description=f"Source: {chunk.file_name}, Page {chunk.page_number}",
                citation_type="pdf"
            )
            results.append({
                "chunk": chunk,
                "score": score,
                "citation": citation
            })

        return results


document_retriever = DocumentRetriever()
