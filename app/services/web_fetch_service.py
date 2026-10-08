import re
import socket
import ipaddress
import urllib.parse
from typing import Dict, Any, Optional
import httpx
from bs4 import BeautifulSoup
from app.utils.config import settings
from app.utils.logger import logger
from app.utils.exceptions import AppException
from app.services.web_search_service import classify_source_type


class WebFetchService:
    """
    Safely fetches readable text and metadata from web pages and papers.
    Includes comprehensive SSRF protection, size caps, and HTML text sanitization.
    """

    BLOCKED_IPS = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("169.254.0.0/16"),   # Link-local / Cloud metadata
        ipaddress.ip_network("0.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
        ipaddress.ip_network("fc00::/7"),
        ipaddress.ip_network("fe80::/10")
    ]

    def __init__(
        self,
        timeout_seconds: int = settings.FETCH_TIMEOUT_SECONDS,
        max_chars: int = settings.MAX_FETCH_CHARS
    ):
        self.timeout = timeout_seconds
        self.max_chars = max_chars

    def validate_url(self, url: str) -> None:
        """
        Validates URL scheme and enforces SSRF defenses against private/loopback IPs.
        """
        if not url or not isinstance(url, str):
            raise AppException("Invalid URL provided.", status_code=400)

        parsed = urllib.parse.urlparse(url.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            raise AppException(f"Disallowed URL scheme '{parsed.scheme}'. Only http and https are allowed.", status_code=400)

        hostname = parsed.hostname
        if not hostname:
            raise AppException("URL must have a valid hostname.", status_code=400)

        # Block literal IP or localhost hostname
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
            raise AppException("SSRF protection: loopback and internal hosts are blocked.", status_code=403)

        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                for blocked in self.BLOCKED_IPS:
                    if ip_obj in blocked:
                        raise AppException(
                            f"SSRF protection: connection to private address {ip_str} is prohibited.",
                            status_code=403
                        )
        except socket.gaierror:
            # Domain not resolving, let HTTP client handle or reject
            pass

    def fetch_url(self, url: str) -> Dict[str, Any]:
        """
        Fetches webpage text and returns clean readable representation.
        """
        self.validate_url(url)

        headers = {
            "User-Agent": "InfinityGPT-ResearchBot/2.0 (+https://github.com/Suryakant-gig/multi_agent-demo)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5"
        }

        try:
            with httpx.Client(timeout=float(self.timeout), follow_redirects=True) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "").lower()
                raw_html = resp.text

        except httpx.HTTPStatusError as e:
            logger.warning(f"Failed to fetch {url}: HTTP {e.response.status_code}")
            return {
                "url": url,
                "title": f"HTTP Error {e.response.status_code}",
                "text": f"Could not fetch document at {url}. Received HTTP status {e.response.status_code}.",
                "metadata": {"status_code": e.response.status_code, "error": True},
                "source_type": classify_source_type(url, ""),
                "content_length": 0
            }
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return {
                "url": url,
                "title": "Fetch Failed",
                "text": f"Error connecting to {url}: {str(e)}",
                "metadata": {"error": str(e)},
                "source_type": classify_source_type(url, ""),
                "content_length": 0
            }

        # Parse text using BeautifulSoup
        soup = BeautifulSoup(raw_html, "html.parser")

        # Extract title
        title_tag = soup.find("title")
        title = title_tag.get_text().strip() if title_tag else ""

        # Remove clutter tags
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "svg"]):
            element.extract()

        # Extract main text
        clean_text = soup.get_text(separator="\n")
        # Collapse excessive whitespace and newlines
        clean_text = re.sub(r"\n\s*\n+", "\n\n", clean_text).strip()

        # Truncate to max characters to prevent token exhaustion
        if len(clean_text) > self.max_chars:
            clean_text = clean_text[:self.max_chars] + "\n\n[Content truncated for length...]"

        source_type = classify_source_type(url, title)

        return {
            "url": url,
            "title": title or url,
            "text": clean_text,
            "metadata": {
                "content_type": content_type,
                "truncated": len(clean_text) >= self.max_chars
            },
            "source_type": source_type,
            "content_length": len(clean_text)
        }


web_fetch_service = WebFetchService()
