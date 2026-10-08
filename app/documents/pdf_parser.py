import os
from typing import List, Dict, Any, Tuple
from pypdf import PdfReader
from app.utils.logger import logger
from app.utils.exceptions import InvalidFileException


class PDFParser:
    """
    Extracts text page by page from PDF files using pypdf.
    Detects scanned or image-only documents where text extraction is unavailable.
    """

    @staticmethod
    def extract_pages(file_path: str) -> Tuple[List[Dict[str, Any]], bool, int]:
        """
        Parses PDF file and extracts text page by page.
        
        Returns:
            Tuple of:
            - List of page dicts: [{"page_number": 1, "text": "...", "char_count": 120}]
            - is_scanned (bool): True if text extraction failed or extracted negligible text
            - total_char_count (int)
        """
        if not os.path.exists(file_path):
            raise InvalidFileException(f"PDF file not found: {file_path}")

        pages: List[Dict[str, Any]] = []
        total_chars = 0

        try:
            reader = PdfReader(file_path)
            if reader.is_encrypted:
                try:
                    reader.decrypt("")
                except Exception:
                    raise InvalidFileException("PDF is password protected and cannot be extracted.")

            page_count = len(reader.pages)
            if page_count == 0:
                raise InvalidFileException("PDF contains no pages.")

            for idx, page in enumerate(reader.pages, start=1):
                try:
                    text = page.extract_text() or ""
                except Exception as ex:
                    logger.warning(f"Failed to extract text from page {idx}: {ex}")
                    text = ""

                clean_text = text.strip()
                char_count = len(clean_text)
                total_chars += char_count

                pages.append({
                    "page_number": idx,
                    "text": clean_text,
                    "char_count": char_count
                })

            # Scanned PDF detection heuristic:
            # If total characters extracted across all pages is zero or average < 20 chars per page,
            # it is almost certainly a scanned image PDF.
            avg_chars = total_chars / page_count if page_count > 0 else 0
            is_scanned = (total_chars == 0) or (page_count > 1 and avg_chars < 20)

            return pages, is_scanned, total_chars

        except InvalidFileException:
            raise
        except Exception as e:
            logger.error(f"Failed to parse PDF {file_path}: {e}")
            raise InvalidFileException(f"Failed to parse PDF document: {str(e)}")


pdf_parser = PDFParser()
