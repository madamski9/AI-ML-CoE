# SAP Firefighter Log Compliance Reviewer

AI-assisted pre-screening tool for SAP GRC Firefighter sessions. Produces structured verdicts (PASS / REJECT / NEEDS_CORRECTION) with per-finding evidence citations, letting human controllers focus on borderline cases instead of reading every log line from scratch.

---

## Quick start

```bash
# Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure LLM (local Ollama)
cp .env.example .env          # set OLLAMA_URL and API_KEY

# Streamlit UI
streamlit run src/app.py

# FastAPI REST backend
uvicorn src.main:app --reload

# CLI — single session
python predict.py --input dataset_candidate/train/sessions/FF-TRAIN-0001.json --output out.jsonl

# Eval harness — one command (train set self-evaluation)
python predict.py \
    --input  dataset_candidate/train/sessions \
    --output predictions_train.jsonl \
    --eval   dataset_candidate/train/labels.jsonl
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        Input sources                         │
│  Streamlit upload │ POST /review (FastAPI) │ predict.py CLI  │
└──────────────────────────────┬───────────────────────────────┘
                               │  Session JSON (validated by Pydantic)
                               ▼
┌──────────────────────────────────────────────────────────────┐
│               ffreviewer.engine.review_session()             │
│                                                              │
│  ┌───────────────────────────┐  ┌──────────────────────────┐ │
│  │   Deterministic rules     │  │    LLM-backed rules      │ │
│  │   R-001, R-003 – R-013   │  │    R-002, R-006          │ │
│  │   Pure Python / regex     │  │    Ollama qwen2.5:7b     │ │
│  │   < 1 ms per session      │  │    disk-cached           │ │
│  └─────────────┬─────────────┘  └────────────┬─────────────┘ │
│                └──────────────┬───────────────┘               │
│                               ▼                               │
│               _determine_verdict(findings)                    │
│               severity-based heuristic                        │
│                               │                               │
│          ┌────────────────────┤                               │
│          │ NEEDS_CORRECTION?  │                               │
│          ▼                    ▼                               │
│   generate_correction()    return Verdict                     │
│   (LLM, disk-cached)                                          │
└──────────────────────────────────────────────────────────────┘
                               │
               ┌───────────────┼───────────────┐
               ▼               ▼               ▼
        Streamlit UI      FastAPI JSON     predict.py
        (app.py)          response         JSONL output
               │
               ▼
      Controller decision
      (PASS / REJECT / SEND BACK)
      saved to decisions.jsonl
```

**Key design decision:** Deterministic checks run first (fast, free, no hallucination risk). LLM is invoked only for two semantically complex checks (module-mismatch classification and volume-proportionality) and for generating the correction message. This keeps median latency under 100 ms for the common PASS path.

---

## Compliance rule catalog

### Baseline rules (R-001 – R-010)

| Rule | Logic | Rationale |
|------|-------|-----------|
| R-001 | Reason code empty, < 20 chars, or matches generic-phrase regex | Most common audit finding; templated reasons give reviewers nothing to verify |
| R-002 | LLM classifies reason into SAP module; mismatch with modules inferred from tcodes | Keyword matching alone can't handle "vendor issue in payment process" → both FI and MM |
| R-003 | Regex on system_log messages for `/h`, "debug", "value modif"; tcode `/H` in transaction_log | Debug & replace bypasses all change-management controls; must be critical regardless of intent |
| R-004 | Tcode SE16N/SM30/SM31 OR change_log entries on known sensitive tables | Direct table edits leave no workflow trace and frequently circumvent approval hierarchies |
| R-005 | tcode SM49/SM69/OS06 OR non-empty os_command_log | OS access from an SAP session is almost never legitimately needed for application-layer fixes |
| R-006 | LLM assesses whether change/tcode counts are proportionate to stated reason | Regex thresholds are arbitrary; LLM can reason "265 vendor masters ≠ fix one vendor" naturally |
| R-007 | Session start outside 07:00–19:59 UTC Mon–Fri AND reason doesn't match emergency keywords | After-hours access is higher risk; the exception (genuine emergency) is explicitly carved out |
| R-008 | `firefighter_user == ticket_requester` (case-insensitive) | Classic four-eyes violation; person requesting their own elevated access removes oversight |
| R-009 | `(end_time − start_time) > 120 min` | Standard SAP GRC auto-extend limit; sessions running past this should have re-justification |
| R-010 | Tcode set-intersection against known SoD conflict pairs | Hardcoded from the Big-4 SAP SoD matrix; pair detection is exact and requires no model |

### Additional rules (R-011 – R-013)

| Rule | Severity | Rationale for inclusion |
|------|----------|------------------------|
| R-011 | critical | Authorization/role transactions (SU01, PFCG, …) during a firefighter session is privilege-escalation-in-progress; not in the baseline but seen in the training data and among the highest-risk actions in any SAP audit |
| R-012 | high | Transport-management transactions (SE09/SE10/STMS) must follow the standard ChaRM process; doing them inside a firefighter session is effectively a shadow change and always a red flag |
| R-013 | medium | Change-log entries outside the session window indicate either clock skew (a data-quality issue reviewers must know about) or log tampering (a serious finding); deterministic to implement and zero false-positive risk on well-formed data |

---

## Deterministic vs. LLM — rationale

| Aspect | Deterministic (11 rules) | LLM (2 rules + correction) |
|--------|--------------------------|----------------------------|
| Rules | R-001, R-003–R-013 | R-002, R-006, correction text |
| Speed | < 1 ms | 200 ms – 2 s (cached: 0 ms) |
| Cost | $0 | ~0 tokens (local Ollama) |
| Reliability | 100% reproducible | Occasional wrong classifications |
| Why this split | These rules require only exact matches, arithmetic, set operations, or simple regex. No ambiguity that needs language understanding. | Module classification (R-002) and volume proportionality (R-006) both require semantic reasoning about free-text fields. A human reviewer uses domain knowledge, not keyword lookup, for these judgments. LLM replicates that. |

Correction text is always LLM-generated because template-based messages are obvious boilerplate that firefighters learn to ignore. A tailored message citing the specific log lines and suggesting a concrete rewrite is more likely to get a useful response.

---

## Known failure modes

### 1. After-hours timezone mismatch (R-007)
The rule checks `start_time.hour` against UTC business hours (07:00–19:59). Production SAP systems often run in the client's local timezone (CET, EST, …). A session starting at `06:30 UTC` for a German client is `08:30 CET` — perfectly within business hours — but R-007 fires anyway. Fix: add a `client_timezone` field to the session schema, or widen the UTC window to 05:00–22:00 as a conservative proxy.

### 2. R-006 skips moderate-volume anomalies (silent miss)
The LLM call for R-006 is guarded by `change_count < 10 AND tcode_count < 20`. A session with 15 changes for a reason that justifies at most 1 (e.g. "fix one blocked vendor" → 15 LFA1 rows) passes the guard silently and never reaches the LLM. This threshold was set to avoid LLM calls on PASS sessions, but it creates a blind spot for medium-scale anomalies.

### 3. Verdict heuristic is not calibrated on data
`_determine_verdict()` maps severity counts to labels using hard-coded thresholds (`critical → REJECT`, `1 high → NEEDS_CORRECTION`, `2+ high → REJECT`). It does not use any training-set statistics. A single high-severity R-012 finding (transport without CR) currently triggers NEEDS_CORRECTION, but the gold label for a nearly identical session is REJECT. A logistic-regression classifier trained on the 50 labelled examples would likely outperform this heuristic.

### 4. R-008 requires `ticket_requester` field
Self-approval is only detected when the session JSON includes the optional `ticket_requester` field. Sessions where this field is absent — or where the requester is embedded in the free-text reason code ("I requested this via INC0042 because…") — are missed entirely.

### 5. R-002 cannot handle legitimately cross-module sessions
A Basis consultant doing a controlled emergency that touches both vendor master (MM) and a payment run (FI) will trigger R-002 even though both modules are clearly mentioned in the reason. The rule currently flags any mismatch between the *primary* inferred module and the session modules, which over-fires on multi-module emergencies.

---

## Cost estimate per session

The LLM backend is a locally-hosted Ollama instance (`qwen2.5:7b`). API cost is **$0**; the only cost is electricity and GPU time.

For reference, if migrated to a cloud API (e.g. Claude Haiku or GPT-4o-mini):

| Path | Calls | Approx. tokens | Cost at $0.15/1M input |
|------|-------|----------------|------------------------|
| PASS (no LLM triggers) | 0 | 0 | $0.000 |
| NEEDS_CORRECTION (R-002 + correction) | 2 | ~1 200 | ~$0.0002 |
| Full hit (R-002 + R-006 + correction) | 3 | ~2 000 | ~$0.0003 |
| Worst case (all LLM checks) | 3 | ~2 500 | ~$0.0004 |

At 80 sessions/month (typical large AMS client) this is under $0.03/month on cloud hosting. Disk-based caching eliminates repeated cost for identical inputs (e.g. re-running the eval harness during development).

---

## What I would build next (given another week)

1. **Calibrated verdict classifier** — replace the severity-counting heuristic with a logistic regression or small gradient-boosted model trained on the 50 labelled examples. Features: one-hot rule IDs, severity counts, session metadata (duration, hour, is_weekend). Even with 50 examples this should outperform the hand-coded thresholds on NEEDS_CORRECTION vs. REJECT boundary cases.

2. **Client timezone support** — add an optional `client_timezone` field to the Session model and adjust R-007 accordingly; eliminates the largest category of false positives on the current data.

3. **Streaming UI with log highlighting** — render the full transaction, change, and system logs in the Streamlit UI with the relevant lines highlighted in the finding's colour. Controllers currently have to mentally match a finding's `evidence` string back to the raw log; this would cut review time significantly.

4. **"Disagree with gold label" appendix** — after running the eval harness, manually review every prediction that differs from the gold label and write up which ones I believe are labelling errors vs. genuine model mistakes. This is explicitly invited by the challenge brief and distinguishes candidates who treat the dataset as ground truth from those who engage critically.

5. **Adversarial input handling** — validate and normalise: out-of-order timestamps (sort before checks), `reason_code` with embedded Unicode control characters, `tcode` fields with leading/trailing whitespace or lowercase variants, and malformed ISO 8601 timestamps (e.g. without timezone marker). Currently any of these silently corrupt specific rule results.
