"""Memory store helpers used by the UI server.

list_memories() returns every memory file with full content.
reset_memory_store() wipes every file in the store so Session 1 can show a
true baseline on each click.
"""

from pathlib import Path

from anthropic import Anthropic


def _store_id() -> str:
    path = Path(__file__).parent / ".memory_store_id"
    if not path.exists():
        raise RuntimeError("Missing .memory_store_id. Run create_agent.py first.")
    return path.read_text().strip()


def list_memories() -> list[dict]:
    client = Anthropic()
    store_id = _store_id()
    page = client.beta.memory_stores.memories.list(
        store_id, path_prefix="/", order_by="path"
    )
    out: list[dict] = []
    for item in page.data:
        if item.type != "memory":
            continue
        retrieved = client.beta.memory_stores.memories.retrieve(
            item.id, memory_store_id=store_id
        )
        content = retrieved.content or ""
        out.append({"path": item.path, "content": content, "size": len(content)})
    return out


def reset_memory_store() -> int:
    """Delete every memory in the store. Returns the count removed."""
    client = Anthropic()
    store_id = _store_id()
    page = client.beta.memory_stores.memories.list(
        store_id, path_prefix="/", order_by="path"
    )
    removed = 0
    for item in page.data:
        if item.type != "memory":
            continue
        client.beta.memory_stores.memories.delete(item.id, memory_store_id=store_id)
        removed += 1
    return removed
