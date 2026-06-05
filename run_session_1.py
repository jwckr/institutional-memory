"""
Session 1 — Baseline.

Starts a Managed Agents session with the memory store ATTACHED so the agent
can read and write /mnt/memory/. Inlines the round1 docs in the user message.

After this session, inspect the memory store to see what the agent saved:
    python inspect_memory.py
or in the Console UI under Memory Stores.

Usage:
    python run_session_1.py
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

DOCS_DIR = Path(__file__).parent / "synthetic-data/round1"
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
    """Yields events as dicts: {"type": "text"|"tool"|"done", ...}.

    `on_event` is also called for each event so callers that prefer a callback
    don't have to consume the iterator.
    """
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
        title="Session 1 — baseline",
        resources=[
            {
                "type": "memory_store",
                "memory_store_id": memory_store_id,
                "access": "read_write",
                "instructions": (
                    "This is your persistent institutional memory. Mounted at "
                    "/mnt/memory/. Check it before starting. Record what you "
                    "learn for future sessions."
                ),
            }
        ],
    )

    user_message = (
        "I'm including our onboarding and policy documents below. Please:\n"
        "1. First, check your memory store at /mnt/memory/ to see what you've "
        "learned in previous sessions.\n"
        "2. Then read the documents below.\n"
        "3. Then answer the question.\n"
        "4. Before you finish, save anything worth remembering to /mnt/memory/.\n\n"
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
                (OUTPUT_DIR / "session1.txt").write_text(
                    f"=== SESSION 1 ===\nQuestion: {question}\n\n"
                    f"--- ANSWER ---\n{final_text}\n"
                )
                out = {"type": "done", "answer": final_text}
                if on_event:
                    on_event(out)
                yield out
                break


def main() -> None:
    print(f"Loading round1 docs from {DOCS_DIR}/...")
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
    print(f"\nSaved to {OUTPUT_DIR / 'session1.txt'}")
    print("\nInspect what the agent remembered:  python inspect_memory.py")
    print("Then run run_session_2.py.")


if __name__ == "__main__":
    main()
