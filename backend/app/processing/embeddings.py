from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

import httpx

from app.settings import settings

BATCH = 32


def needs_nomic_prefix(model: str) -> bool:
    m = model.lower()
    return "nomic-embed-text" in m or m.startswith("nomic-embed")


def apply_prefix(text: str, kind: Literal["query", "document"]) -> str:
    if needs_nomic_prefix(settings.embedding_model):
        tag = "search_query" if kind == "query" else "search_document"
        return f"{tag}: {text}"
    return text


async def embed_batch(
    client: httpx.AsyncClient, inputs: list[str]
) -> list[list[float]]:
    if not inputs:
        return []
    try:
        r = await client.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": settings.embedding_model, "input": inputs},
            timeout=settings.slow_upstream_request_timeout,
        )
    except httpx.ConnectError as e:
        raise RuntimeError(
            "Embedding service unreachable at "
            f"{settings.ollama_base_url}/api/embed. Ensure settings.ollama_base_url is routable "
            "from the API container and Ollama listens on 0.0.0.0:11434."
        ) from e
    r.raise_for_status()
    data = r.json()
    embeds = data.get("embeddings") or []
    if len(embeds) != len(inputs):
        raise RuntimeError(
            f"Ollama embed: expected {len(inputs)} vectors, got {len(embeds)}"
        )
    return [[float(x) for x in vec] for vec in embeds]


async def embed_texts(
    texts: Iterable[str], kind: Literal["query", "document"] = "document"
) -> list[list[float]]:
    """Embed a batch of texts.

    ``kind`` controls the nomic task prefix.  Chunks should pass ``"document"``
    (the default) at ingest time; ``embed_query`` overrides to ``"query"``.
    """
    items = [apply_prefix(t, kind) for t in texts]
    if not items:
        return []
    out: list[list[float]] = []
    async with httpx.AsyncClient() as client:
        for start in range(0, len(items), BATCH):
            batch = items[start : start + BATCH]
            out.extend(await embed_batch(client, batch))
    return out


async def embed_query(text: str) -> list[float]:
    vecs = await embed_texts([text], kind="query")
    return vecs[0] if vecs else []
