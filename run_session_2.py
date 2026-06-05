"""
Session 2 — After memory + new context.

Same agent, same memory store, fresh session. Round2 docs contradict round1.
The agent should:
- Read memory first (`/mnt/memory/`)
- Notice the contradictions in the new docs
- UPDATE memory rather than appending
- Lead its answer with what changed and why

Usage:
    python run_session_2.py
"""

import os
from pathlib import Path
from typing import Callable, Iterator

from anthropic import Anthropic


TEST_QUESTION = (
    "I just joined the company and I need read-only prod access to debug an "
    "issue tomorrow. What do I do? Be specific about the steps and the people "
    "I need to talk to."
)

DOCS_DIR = Path(__file__).parent / "synthetic-data/round2"
OUTPUT_DIR = Path(__file__).parent / "outputs"


def load_docs_as_context(docs_dir: Path) -> str:
    blocks = []
    for path in sorted(docs_dir.glob("*.md")):
        blocks.append(f"=====  DOCUMENT: {path.name}  =====\n{path.read_text()}")
    return "\n\n".join(blocks)


def stream_session(
    question: str = TEST_QUESTION,
    on_event: Callable[[dict], None] | None = None,
) -> Iterator[dict]:
    """Yields events as dicts: {"type": "text"|"tool"|"done", ...}."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    base = Path(__file__).parent
    for required in (".agent_id", ".environment_id", ".memory_store_id"):
        if not (base / required).exists():
            raise RuntimeError(f"Missing {required}. Run create_agent.py first.")

    agent_id = (base / ".agent_id").read_text().strip()
    environment_id = (base / ".environment_id").read_text().strip()
    memory_store_id = (base / ".memory_store_id").read_text().strip()

    client = Anthropic()
    context = load_docs_as_context(DOCS_DIR)

    session = client.beta.sessions.create(
        agent=agent_id,
        environment_id=environment_id,
        title="Session 2 — after memory + new context",
        resources=[
            {
                "type": "memory_store",
                "memory_store_id": memory_store_id,
                "access": "read_write",
                "instructions": (
                    "This is your persistent institutional memory. Some entries "
                    "may be out of date — reconcile against the new documents in "
                    "this session and UPDATE existing entries (don't just append)."
                ),
            }
        ],
    )

    user_message = (
        "I'm including some updated and new documents below. Some of them "
        "contradict things you learned in our previous session.\n\n"
        "Please:\n"
        "1. First, check your memory store at /mnt/memory/ to see what you "
        "already know.\n"
        "2. Read the new documents below.\n"
        "3. Reconcile conflicts — UPDATE memory entries to reflect the "
        "newer information. Note dates.\n"
        "4. Answer the question.\n"
        "5. If your answer differs from your previous answer, lead with what "
        "changed and why.\n\n"
        f"{context}\n\n"
        "==================================================\n"
        f"QUESTION: {question}"
    )

    final_text_parts: list[str] = []
    with client.beta.sessions.events.stream(session.id) as stream:
        client.beta.sessions.events.send(
            session.id,
            events=[
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": user_message}],
                }
            ],
        )
        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if getattr(block, "type", None) == "text":
                        final_text_parts.append(block.text)
                        out = {"type": "text", "text": block.text}
                        if on_event:
                            on_event(out)
                        yield out
            elif event.type == "agent.tool_use":
                name = getattr(event, "name", "?")
                inp = getattr(event, "input", {}) or {}
                target = (
                    inp.get("path")
                    or inp.get("file_path")
                    or inp.get("command")
                    or ""
                )
                is_memory = "/mnt/memory" in str(target)
                out = {
                    "type": "tool",
                    "name": name,
                    "target": str(target),
                    "is_memory": is_memory,
                }
                if on_event:
                    on_event(out)
                yield out
            elif event.type == "session.status_idle":
                final_text = "".join(final_text_parts)
                OUTPUT_DIR.mkdir(exist_ok=True)
                (OUTPUT_DIR / "session2.txt").write_text(
                    f"=== SESSION 2 ===\nQuestion: {question}\n\n"
                    f"--- ANSWER ---\n{final_text}\n"
                )
                out = {"type": "done", "answer": final_text}
                if on_event:
                    on_event(out)
                yield out
                break


def main() -> None:
    print(f"Loading round2 docs from {DOCS_DIR}/...")
    for path in sorted(DOCS_DIR.glob("*.md")):
        print(f"  including {path.name}")
    print("\nAgent working...\n")
    for ev in stream_session():
        if ev["type"] == "text":
            print(ev["text"], end="", flush=True)
        elif ev["type"] == "tool":
            label = (
                f"[memory: {ev['name']}  {ev['target']}]"
                if ev["is_memory"]
                else f"[{ev['name']}]"
            )
            print(f"\n  {label}", flush=True)
        elif ev["type"] == "done":
            print("\n\n[agent finished]")
    print(f"\nSaved to {OUTPUT_DIR / 'session2.txt'}")
    print("\nDiff outputs/session1.txt and outputs/session2.txt — the demo lives there.")
    print("Inspect updated memory:  python inspect_memory.py")


if __name__ == "__main__":
    main()
