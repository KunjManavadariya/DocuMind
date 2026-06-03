from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    token_count: int


def tokenize(text: str) -> list[str]:
    return re.findall(r"\S+", text)


def chunk_text(text: str, chunk_size: int = 256, chunk_overlap: int = 40) -> list[TextChunk]:
    tokens = tokenize(text)
    if not tokens:
        return []

    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    chunks: list[TextChunk] = []
    start = 0
    index = 0
    step = chunk_size - chunk_overlap

    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(
            TextChunk(
                index=index,
                content=" ".join(chunk_tokens),
                token_count=len(chunk_tokens),
            )
        )
        if end == len(tokens):
            break
        start += step
        index += 1

    return chunks

