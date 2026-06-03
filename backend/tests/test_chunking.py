import pytest

from app.chunking import chunk_text


def test_chunk_text_splits_with_overlap() -> None:
    text = " ".join(f"token{i}" for i in range(10))

    chunks = chunk_text(text, chunk_size=4, chunk_overlap=1)

    assert [chunk.token_count for chunk in chunks] == [4, 4, 4]
    assert chunks[0].content == "token0 token1 token2 token3"
    assert chunks[1].content == "token3 token4 token5 token6"


def test_chunk_text_rejects_overlap_equal_to_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_text("hello world", chunk_size=4, chunk_overlap=4)
