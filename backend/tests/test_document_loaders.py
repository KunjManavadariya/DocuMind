import pytest
import httpx

from app.document_loaders import fetch_url_document, load_uploaded_document, load_url_document


def test_load_uploaded_markdown_document() -> None:
    loaded = load_uploaded_document(
        "guide.md",
        b"# Guide\n\nUse Redis for Celery and pgvector for retrieval.",
    )

    assert loaded.title == "guide"
    assert loaded.source_type == "upload"
    assert loaded.source_uri == "upload://guide.md"
    assert "pgvector" in loaded.content


def test_load_uploaded_document_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="No extractable text"):
        load_uploaded_document("empty.txt", b"   ")


def test_load_uploaded_document_rejects_unknown_extension() -> None:
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_uploaded_document("notes.docx", b"content")


def test_load_url_html_document_extracts_title_and_text() -> None:
    loaded = load_url_document(
        "https://docs.example.com/guide",
        b"""
        <html>
          <head><title>DocuMind Guide</title><style>.hidden{}</style></head>
          <body>
            <h1>Guide</h1>
            <p>Use pgvector for semantic search.</p>
            <script>ignoreMe()</script>
          </body>
        </html>
        """,
        content_type="text/html",
    )

    assert loaded.title == "DocuMind Guide"
    assert loaded.source_type == "url"
    assert loaded.source_uri == "https://docs.example.com/guide"
    assert "Use pgvector for semantic search" in loaded.content
    assert "ignoreMe" not in loaded.content


def test_fetch_url_document_uses_http_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://docs.example.com"
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=b"<title>Docs Home</title><main>Redis caches answers.</main>",
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        fetched = fetch_url_document("https://docs.example.com", client=client)

    assert fetched.title == "Docs Home"
    assert fetched.filename == "index.html"
    assert fetched.content_type == "text/html"
    assert "Redis caches answers" in fetched.content


def test_fetch_url_document_rejects_relative_url() -> None:
    with pytest.raises(ValueError, match="absolute http or https"):
        fetch_url_document("/docs")
