from __future__ import annotations

import io
from dataclasses import dataclass
import re
from typing import Optional
import httpx
from pypdf import PdfReader
from logger_config import get_logger
from bs4 import BeautifulSoup

logger = get_logger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(30.0, read=60.0)
MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024


@dataclass
class PdfText:
    url: str
    text: str
    pages: int

def _download_pdf(url: str, client: Optional[httpx.Client] = None) -> bytes:
    """Stream-download a PDF from a URL into memory (no disk use). Synchronous version."""
    close_client = False
    if client is None:
        client = httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True)
        close_client = True

    logger.info(f"Starting download: {url}")

    try:
        try:
            head = client.head(url)
            if not (200 <= head.status_code < 400):
                logger.warning(f"HEAD request failed for {url}, continuing with GET.")
                head = None
        except Exception as e:
            logger.warning(f"HEAD request error for {url}: {e}")
            head = None

        if head is not None:
            ctype = head.headers.get("content-type", "").lower()
            length = head.headers.get("content-length")
            if length is not None and int(length) > MAX_DOWNLOAD_SIZE:
                raise ValueError(f"File too large: {length} bytes (limit {MAX_DOWNLOAD_SIZE})")
            
            if length is not None and int(length) == 0:
                raise ValueError(f"File at {url} is empty (0 bytes).")
            
            if (
                "pdf" not in ctype
                and "text" not in ctype
                and "html" not in ctype
                and "octet-stream" not in ctype
            ):
                logger.warning(f"Unexpected content-type ({ctype}), proceeding anyway...")

        # Stream the download into memory safely
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = 0
            chunks = []
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > MAX_DOWNLOAD_SIZE:
                    raise ValueError("Download exceeded size limit (50 MB)")
                chunks.append(chunk)

        logger.info(f"Successfully downloaded {total / 1024:.2f} KB from {url}")
        data = b"".join(chunks)
        
        if not data or len(data) < 500:
            raise ValueError(f"Downloaded file from {url} is too small or empty ({len(data)} bytes).")

        if not data.strip().startswith(b"%PDF"):
            logger.warning(f"File from {url} does not start with '%PDF', may not be a valid PDF.")
                
        return data

    except Exception as e:
        logger.exception(f"Failed to download PDF from {url}: {e}")
        raise
    finally:
        if close_client:
            client.close()


def _extract_text_pypdf(data: bytes) -> tuple[str, int]:
    """Extract text using pypdf."""
    try:
        reader = PdfReader(io.BytesIO(data))
        texts = []
        for i, page in enumerate(reader.pages):
            try:
                texts.append(page.extract_text() or "")
            except Exception as e:
                logger.warning(f"Failed to extract text from page {i + 1}: {e}")
                texts.append("")
        text = "\n".join(t.strip() for t in texts if t)
        logger.info(f"Extracted text from {len(reader.pages)} pages using PyPDF.")
        return text, len(reader.pages)
    except Exception as e:
        logger.exception(f"PyPDF extraction failed: {e}")
        raise


def _fallback_pdfminer(data: bytes) -> tuple[str, int]:
    """Fallback to pdfminer if pypdf fails."""
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text
        text = pdfminer_extract_text(io.BytesIO(data)) or ""
        try:
            reader = PdfReader(io.BytesIO(data))
            pages = len(reader.pages)
        except Exception:
            pages = 0
        logger.info("Fallback to pdfminer succeeded.")
        return text, pages
    except Exception as e:
        logger.exception(f"Failed to extract text with pdfminer: {e}")
        raise RuntimeError(f"Failed to extract text with pdfminer: {e}")


def _sanitize_text(text: str) -> str:
    """Remove NUL and other control characters that break PostgreSQL."""
    # Remove NUL (0x00) and other problematic control characters
    # Keep tab (0x09), newline (0x0A), and carriage return (0x0D)
    sanitized = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
    return sanitized.strip()


def fetch_pdf_text(url: str) -> PdfText:
    """
    Synchronous function that:
    - Downloads a PDF (streamed)
    - Detects if it's actually HTML or plain text instead of a PDF
    - Extracts text appropriately (PDF via PyPDF/pdfminer, HTML via BeautifulSoup)
    - Returns PdfText dataclass with sanitized text
    """
    try:
        data = _download_pdf(url)
    except Exception as e:
        logger.error(f"Download failed for {url}: {e}")
        raise

    try:
        decoded = data.decode("utf-8", errors="ignore").strip()
        if len(decoded) > 0:
            # Check if HTML content
            if "<html" in decoded.lower() or "<body" in decoded.lower():
                soup = BeautifulSoup(decoded, "html.parser")
                text = soup.get_text(separator="\n", strip=True)
                text = _sanitize_text(text)
                logger.info(f"Extracted text from HTML page: {url}")
                return PdfText(url=url, text=text, pages=1)

            if all(ch.isprintable() or ch.isspace() for ch in decoded[:1000]):
                logger.info(f"Detected plain text content instead of PDF: {url}")
                text = _sanitize_text(decoded)
                return PdfText(url=url, text=text, pages=1)
    except Exception as e:
        logger.warning(f"Text/HTML detection failed, assuming PDF: {e}")
        
    try:
        text, pages = _extract_text_pypdf(data)
        text = _sanitize_text(text)
        if text:
            return PdfText(url=url, text=text, pages=pages)
    except Exception:
        logger.warning(f"PyPDF extraction failed for {url}, switching to pdfminer...")

    try:
        text, pages = _fallback_pdfminer(data)
        text = _sanitize_text(text)
        if not text:
            raise ValueError("No text could be extracted from this file.")
        return PdfText(url=url, text=text, pages=pages)
    
    except Exception as e:
        logger.warning(f"Skipping {url}: both PyPDF and pdfminer failed. Reason: {e}")


def _sync_main():
    import argparse

    parser = argparse.ArgumentParser(description="Synchronous PDF text fetcher")
    parser.add_argument("url", help="URL of the PDF to fetch")
    parser.add_argument("--out", type=str, help="File to write extracted text to")
    args = parser.parse_args()

    result: PdfText = fetch_pdf_text(args.url)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result.text)
        logger.info(f"Wrote {result.pages} pages of text to {args.out}")
    else:
        logger.info(f"Fetched {result.pages} pages from {args.url}")
        preview = result.text[:2000]
        print(preview)


if __name__ == "__main__":
    _sync_main()
