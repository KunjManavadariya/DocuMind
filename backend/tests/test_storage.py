from pathlib import Path

from app.storage import LocalDocumentStorage, R2DocumentStorage


def test_local_document_storage_writes_upload(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(root_dir=tmp_path)

    uri = storage.store_upload(
        filename="My Notes.md",
        data=b"# Notes",
        content_type="text/markdown",
    )

    assert uri.startswith("local://uploads/")
    stored_path = tmp_path / uri.removeprefix("local://")
    assert stored_path.read_bytes() == b"# Notes"
    assert stored_path.name.endswith("-My-Notes.md")


def test_r2_document_storage_puts_object_with_content_type() -> None:
    calls = {}

    class FakeClient:
        def put_object(self, **kwargs):
            calls.update(kwargs)

    storage = R2DocumentStorage(
        endpoint_url="https://example.r2.cloudflarestorage.com",
        access_key_id="access",
        secret_access_key="secret",
        bucket="documind",
        client=FakeClient(),
    )

    uri = storage.store_upload(
        filename="notes.md",
        data=b"# Notes",
        content_type="text/markdown",
    )

    assert uri.startswith("r2://documind/uploads/")
    assert calls["Bucket"] == "documind"
    assert calls["Body"] == b"# Notes"
    assert calls["ContentType"] == "text/markdown"
    assert calls["Key"].endswith("-notes.md")
