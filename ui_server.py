"""Flask UI server for the Institutional Memory Agent demo.

Routes:
  GET  /                  -> static UI
  GET  /api/memory        -> {memories: [{path, content, size}]}
  POST /api/reset         -> wipes the memory store
  GET  /api/session1?q=.. -> SSE stream of session 1 events
  GET  /api/session2?q=.. -> SSE stream of session 2 events

Session endpoints are GET because EventSource (browser SSE) is GET-only.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python ui_server.py
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

import run_session_1
import run_session_2
from memory_helpers import list_memories, reset_memory_store


HERE = Path(__file__).parent
STATIC_DIR = HERE / "ui_static"

app = Flask(__name__, static_folder=None)


def _sse(payload: dict) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode("utf-8")


def _stream(question: str, runner, label: str):
    # Snapshot memory before the run so the UI can diff.
    try:
        before = list_memories()
    except Exception as e:  # noqa: BLE001
        before = []
        yield _sse({"type": "warn", "msg": f"memory snapshot failed: {e}"})

    yield _sse({"type": "started", "label": label, "memory_before": before})

    try:
        for ev in runner.stream_session(question):
            yield _sse(ev)
    except Exception as e:  # noqa: BLE001
        yield _sse({"type": "error", "msg": str(e), "trace": traceback.format_exc()})
        return

    try:
        after = list_memories()
    except Exception as e:  # noqa: BLE001
        after = before
        yield _sse({"type": "warn", "msg": f"post-run memory read failed: {e}"})

    yield _sse({"type": "finished", "memory_after": after})


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:filename>")
def static_files(filename: str):
    return send_from_directory(STATIC_DIR, filename)


@app.route("/api/memory")
def api_memory():
    return jsonify({"memories": list_memories()})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    removed = reset_memory_store()
    return jsonify({"removed": removed})


@app.route("/api/session1")
def api_session1():
    question = request.args.get("q", "").strip()
    if not question:
        return jsonify({"error": "missing q"}), 400
    # Reset memory before session 1 so each baseline run starts clean.
    try:
        reset_memory_store()
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": f"reset failed: {e}"}), 500
    return Response(
        _stream(question, run_session_1, "Session 1 — baseline"),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/api/session2")
def api_session2():
    question = request.args.get("q", "").strip()
    if not question:
        return jsonify({"error": "missing q"}), 400
    return Response(
        _stream(question, run_session_2, "Session 2 — after memory + new docs"),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
