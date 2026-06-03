from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader


SUPPORTED_UPLOAD_EXTENSIONS = {".txt", ".md", ".markdown", ".pdf"}


@dataclass(frozen=True)
class LoadedDocument:
    title: str
    content: str
    source_type: str
    source_uri: str | None


@dataclass(frozen=True)
class FetchedUrlDocument:
    title: str
    content: str
    source_type: str
    source_uri: str
    filename: str
    data: bytes
    content_type: str | None


def load_uploaded_document(filename: str, data: bytes) -> LoadedDocument:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_UPLOAD_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_UPLOAD_EXTENSIONS))
        raise ValueError(f"Unsupported file type '{extension}'. Supported types: {supported}")

    if extension == ".pdf":
        content = _extract_pdf_text(data)
    else:
        content = _decode_text(data)

    content = content.strip()
    if not content:
        raise ValueError("No extractable text found in uploaded document")

    return LoadedDocument(
        title=Path(filename).stem or filename,
        content=content,
        source_type="upload",
        source_uri=f"upload://{filename}",
    )


def fetch_url_document(
    url: str,
    *,
    timeout_seconds: float = 10.0,
    max_bytes: int = 2_000_000,
    client: httpx.Client | None = None,
) -> FetchedUrlDocument:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be an absolute http or https URL")

    owns_client = client is None
    http_client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
    try:
        response = http_client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ValueError(f"Could not fetch URL: {exc}") from exc
    finally:
        if owns_client:
            http_client.close()

    data = response.content
    if len(data) > max_bytes:
        raise ValueError(f"Fetched document is too large; max size is {max_bytes} bytes")

    content_type = response.headers.get("content-type")
    loaded = load_url_document(
        url=str(response.url),
        data=data,
        content_type=content_type,
    )
    return FetchedUrlDocument(
        title=loaded.title,
        content=loaded.content,
        source_type=loaded.source_type,
        source_uri=loaded.source_uri or str(response.url),
        filename=_filename_from_url(str(response.url), content_type=content_type),
        data=data,
        content_type=content_type,
    )


def load_url_document(url: str, data: bytes, content_type: str | None = None) -> LoadedDocument:
    text = _decode_text(data)
    title = _title_from_url(url)

    if content_type and "html" in content_type.lower():
        extractor = _HTMLTextExtractor()
        extractor.feed(text)
        content = extractor.text
        title = extractor.title or title
    else:
        content = text

    content = _normalize_text(content)
    if not content:
        raise ValueError("No extractable text found in fetched document")

    return LoadedDocument(
        title=title,
        content=content,
        source_type="url",
        source_uri=url,
    )


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    page_text = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(page_text)


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).stem
    return name or parsed.netloc or "Fetched Document"


def _filename_from_url(url: str, *, content_type: str | None) -> str:
    parsed = urlparse(url)
    name = Path(parsed.path).name
    if name:
        return name
    if content_type and "html" in content_type.lower():
        return "index.html"
    return "fetched-document.txt"


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    @property
    def text(self) -> str:
        return " ".join(self.parts)

    @property
    def title(self) -> str:
        return _normalize_text(" ".join(self.title_parts))

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._ignored_depth > 0:
            self._ignored_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth > 0:
            return
        if self._in_title:
            self.title_parts.append(data)
        else:
            self.parts.append(data)
