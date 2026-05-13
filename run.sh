#!/usr/bin/env bash
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:7b}"
OLLAMA_PID=""

cleanup() {
    echo ""
    echo "Shutting down..."
    kill "$FASTAPI_PID" "$STREAMLIT_PID" 2>/dev/null
    [ -n "$OLLAMA_PID" ] && kill "$OLLAMA_PID" 2>/dev/null
    wait 2>/dev/null
    echo "Done."
}
trap cleanup EXIT INT TERM

if curl -sf http://localhost:11434 > /dev/null 2>&1; then
    echo "Ollama already running — skipping start."
else
    echo "Starting Ollama..."
    ollama serve > /tmp/ollama.log 2>&1 &
    OLLAMA_PID=$!
    for i in $(seq 1 15); do
        curl -sf http://localhost:11434 > /dev/null 2>&1 && break
        sleep 1
    done
    if ! curl -sf http://localhost:11434 > /dev/null 2>&1; then
        echo "ERROR: Ollama did not start in time. Check /tmp/ollama.log"
        exit 1
    fi
    echo "Ollama ready. Pulling $OLLAMA_MODEL if needed..."
    ollama pull "$OLLAMA_MODEL" --quiet
fi

uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload &
FASTAPI_PID=$!

streamlit run src/app.py --server.port 8501 --server.headless true &
STREAMLIT_PID=$!

echo ""
echo "  Ollama:           http://localhost:11434  (model: $OLLAMA_MODEL)"
echo "  FastAPI backend:  http://localhost:8000"
echo "  FastAPI docs:     http://localhost:8000/docs"
echo "  Streamlit UI:     http://localhost:8501"
echo ""
echo "Press Ctrl+C to stop."

wait "$FASTAPI_PID" "$STREAMLIT_PID"