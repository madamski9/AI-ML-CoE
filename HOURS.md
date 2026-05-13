# Hours log

| Date       | Hours | Phase | What I did |
|------------|-------|-------|------------|
| 2026-05-11 | 0.5   | Setup | Repo scaffold, venv, requirements |
| 2026-05-11 | 2.0   | Ollama | Installed Ollama, pulled qwen2.5:7b, configured .env, wired up OpenAI-compatible client with disk cache and retry logic |
| 2026-05-11 | 5.0   | Deterministic | Implemented R-001–R-013: reason code quality, debug detection, direct table edits, OS commands, after-hours, self-approval, session duration, SoD pairs, auth transactions, transport CR check, change-log timestamp anomaly |
| 2026-05-12 | 2.0   | Semantic | LLM-backed R-002 (module mismatch) and R-006 (volume anomaly); classify_reason_module and generate_correction helpers |
| 2026-05-12 | 4.0   | Ui/FastApi | FastAPI REST backend (/review, /decisions), Streamlit UI with finding cards, confidence bar, controller decision buttons |
| 2026-05-13 | 3.0   | Eval & Polish | Written README (architecture diagram, rule catalog, deterministic vs LLM rationale, failure modes, cost estimate); batch predict.py script with --eval flag; fixed R-004/R-007/R-010/R-011 false positives after running eval on train set (Macro F1 0.556 → 0.784); expanded decisions.jsonl schema to include full AI verdict + findings + override flag; run.sh one-command startup for Ollama + FastAPI + Streamlit |
| 2026-05-13 | 0.5   | Predictions | Generated predictions_train.jsonl (50 sessions) and predictions_test.jsonl (25 sessions); added eval results table and hours log to README |
---
**Total: 17.0 h**