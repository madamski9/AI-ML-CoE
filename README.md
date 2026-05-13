<div align="center">

# SAP Firefighter Log Compliance Reviewer

### AI-assisted pre-screening tool for SAP GRC Firefighter sessions.
Produces structured verdicts (**PASS / REJECT / NEEDS_CORRECTION**) with per-finding evidence citations,
letting human controllers focus on borderline cases instead of reading every log line from scratch.

</div>

---

## Tech Stack

<div align="center">

| Area | Technology |
|:---:|:---:|
| Frontend UI | <img height="40" src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"> |
| Backend API | <img height="40" src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white"><img height="40" src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white"><img height="40" src="https://img.shields.io/badge/Pydantic-E92063?style=for-the-badge&logo=pydantic&logoColor=white"> |
| Compliance Rules | <img height="40" src="https://img.shields.io/badge/Regex%20%2F%20Python-3776AB?style=for-the-badge&logo=python&logoColor=white"> |
| LLM Inference | <img height="40" src="https://img.shields.io/badge/Ollama-000000?style=for-the-badge&logo=ollama&logoColor=white"><img height="40" src="https://img.shields.io/badge/qwen2.5:7b-412991?style=for-the-badge"> |
| Infrastructure | <img height="40" src="https://img.shields.io/badge/Shell-121011?style=for-the-badge&logo=gnu-bash&logoColor=white"> |

</div>

---

## Screenshots

### Main Screen
<div align="center">
    <img width="750" alt="zrzut1" src="https://github.com/user-attachments/assets/6900bf95-e7b2-4219-a11f-f33dfb98764b" />
</div>
---

### Findings
<div align="center">
    <img width="750" alt="zrzut2" src="https://github.com/user-attachments/assets/4a629bab-a4f2-425d-aa31-83395df17257" />
</div>
---

### Suggested Correction & Verdict
<div align="center">
    <img width="750" alt="zrzut3" src="https://github.com/user-attachments/assets/67ef31ef-2f0b-49ac-9015-162ca0fa183f" />
</div>
---

## Overview

The reviewer runs each session through a two-layer pipeline: fast deterministic rules (regex, arithmetic, set operations) handle 11 of 13 checks in under 1 ms, and an LLM is invoked only for the two checks that require semantic reasoning — module classification (R-002) and volume proportionality (R-006). Correction messages are always LLM-generated to avoid boilerplate that firefighters learn to ignore.

---

## Quick Start

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

# Eval harness — full train set
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
┌───────────────────────────────────────────────────────────────┐
│               ffreviewer.engine.review_session()              │
│                                                               │
│  ┌───────────────────────────┐  ┌──────────────────────────┐  │
│  │   Deterministic rules     │  │    LLM-backed rules      │  │
│  │   R-001, R-003 – R-013    │  │    R-002, R-006          │  │
│  │   Pure Python / regex     │  │    Ollama qwen2.5:7b     │  │
│  │   < 1 ms per session      │  │    disk-cached           │  │
│  └─────────────┬─────────────┘  └─────────────┬────────────┘  │
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
```

**Key design decision:** Deterministic checks run first (fast, free, no hallucination risk). LLM is invoked only for two semantically complex checks and for generating the correction message. This keeps median latency under 100 ms for the common PASS path.

---

## Compliance Rule Catalog

### Baseline rules (R-001 – R-010)

| Rule | Logic | Rationale |
|------|-------|-----------|
| R-001 | Reason code empty, < 20 chars, or matches generic-phrase regex | Templated reasons give reviewers nothing to verify |
| R-002 | LLM classifies reason into SAP module; mismatch with modules inferred from tcodes | Keyword matching can't handle ambiguous cross-module phrasing |
| R-003 | Regex on system_log for `/h`, "debug", "value modif"; tcode `/H` in transaction_log | Debug & replace bypasses all change-management controls |
| R-004 | Tcode SE16N/SM30/SM31 OR change_log entries on known sensitive tables | Direct table edits leave no workflow trace |
| R-005 | Tcode SM49/SM69/OS06 OR non-empty os_command_log | OS access from an SAP session is almost never legitimate |
| R-006 | LLM assesses whether change/tcode counts are proportionate to stated reason | "265 vendor masters ≠ fix one vendor" requires semantic reasoning |
| R-007 | Session start outside 07:00–19:59 UTC Mon–Fri AND reason lacks emergency keywords | After-hours access is higher risk; genuine emergencies are carved out |
| R-008 | `firefighter_user == ticket_requester` (case-insensitive) | Classic four-eyes violation |
| R-009 | `(end_time − start_time) > 120 min` | Sessions past the GRC auto-extend limit need re-justification |
| R-010 | Tcode set-intersection against known SoD conflict pairs | Hardcoded from the Big-4 SAP SoD matrix |

### Additional rules (R-011 – R-013)

| Rule | Severity | Rationale |
|------|----------|-----------|
| R-011 | critical | Authorization/role transactions (SU01, PFCG, …) inside a firefighter session = privilege escalation in progress |
| R-012 | high | Transport transactions (SE09/SE10/STMS) must follow ChaRM; doing them here is a shadow change |
| R-013 | medium | Change-log entries outside the session window indicate clock skew or log tampering |

---

## Deterministic vs. LLM

| Aspect | Deterministic (11 rules) | LLM (2 rules + correction) |
|--------|--------------------------|----------------------------|
| Rules | R-001, R-003 – R-013 | R-002, R-006, correction text |
| Speed | < 1 ms | 200 ms – 2 s (cached: 0 ms) |
| Cost | $0 | ~$0 (local Ollama) |
| Reliability | 100% reproducible | Occasional wrong classifications |
| Why | Exact matches, arithmetic, regex | Free-text semantic reasoning |

---

## Cost Estimate

The LLM backend is a locally-hosted Ollama instance. API cost is **$0**. For reference, if migrated to a cloud API:

| Path | Calls | Approx. tokens | Cost at $0.15/1M input |
|------|-------|----------------|------------------------|
| PASS (no LLM triggers) | 0 | 0 | $0.000 |
| NEEDS_CORRECTION | 2 | ~1 200 | ~$0.0002 |
| Full hit (R-002 + R-006 + correction) | 3 | ~2 000 | ~$0.0003 |

At 80 sessions/month (typical large AMS client) this is **under $0.03/month** on cloud hosting.

---

<<<<<<< Updated upstream
## Known Failure Modes
=======
## Train-set evaluation results

Run with: `python predict.py --input dataset_candidate/train/sessions --output predictions_train.jsonl --eval dataset_candidate/train/labels.jsonl`

```
Total sessions : 50
Accuracy       : 0.78
Macro F1       : 0.784

Per-class:
  PASS              P=0.842  R=0.800  F1=0.821  (support=20)
  REJECT            P=1.000  R=0.733  F1=0.846  (support=15)
  NEEDS_CORRECTION  P=0.600  R=0.800  F1=0.686  (support=15)

Confusion matrix (rows=gold, cols=pred):
                   PASS  REJECT  NEEDS_CORRECTION
  PASS               16       0                 4
  REJECT              0      11                 4
  NEEDS_CORRECTION    3       0                12

Per-rule metrics:
  rule    P      R      F1    TP  FP  FN  support
  R-001   1.000  0.643  0.783  9   0   5   14
  R-002   0.200  0.222  0.211  2   8   7    9
  R-003   1.000  1.000  1.000  3   0   0    3
  R-004   1.000  1.000  1.000  4   0   0    4
  R-005   1.000  1.000  1.000  2   0   0    2
  R-006   1.000  1.000  1.000  2   0   0    2
  R-007   0.667  1.000  0.800 10   5   0   10
  R-008   1.000  1.000  1.000  2   0   0    2
  R-009   1.000  1.000  1.000  3   0   0    3
  R-010   0.500  1.000  0.667  2   2   0    2
```

Notable: R-002 (module mismatch, LLM-backed) has the lowest precision — the local qwen2.5:7b model occasionally misclassifies the SAP module from the reason code, generating false positives. R-001 recall is 0.643 because some genuinely vague reason codes are long enough to pass the length check but still lack operational specifics.

---

## What I would build next (given another week)
>>>>>>> Stashed changes

**1. After-hours timezone mismatch (R-007)**
The rule checks `start_time.hour` against UTC business hours. A session at `06:30 UTC` for a German client is `08:30 CET` — business hours — but R-007 fires anyway. Fix: add `client_timezone` to the session schema, or widen the UTC window to `05:00–22:00` as a conservative proxy.

**2. R-006 misses moderate-volume anomalies**
The LLM guard fires only when `change_count < 10 AND tcode_count < 20`. A session with 15 changes for a reason justifying at most 1 passes silently. This threshold was set to avoid LLM calls on clean sessions, but it creates a blind spot for medium-scale anomalies.

**3. Verdict heuristic is uncalibrated**
`_determine_verdict()` uses hard-coded thresholds (`critical → REJECT`, `1 high → NEEDS_CORRECTION`, `2+ high → REJECT`). A logistic-regression classifier trained on the 50 labelled examples would likely outperform these thresholds on NEEDS_CORRECTION vs. REJECT boundary cases.

**4. R-008 requires `ticket_requester` field**
Self-approval is only detected when the optional `ticket_requester` field is present. Sessions where the requester is embedded in free-text reason code are missed entirely.

<<<<<<< Updated upstream
**5. R-002 over-fires on multi-module sessions**
A Basis consultant doing a controlled emergency touching both MM and FI will trigger R-002 even though both modules appear in the reason. The rule currently flags any mismatch against the *primary* inferred module.

---

## What I Would Build Next

1. **Calibrated verdict classifier** — replace the severity-counting heuristic with a logistic regression or small gradient-boosted model trained on the 50 labelled examples.
2. **Client timezone support** — add `client_timezone` to the Session model and adjust R-007; eliminates the largest false-positive category.
3. **Streaming UI with log highlighting** — render transaction, change, and system logs with relevant lines highlighted per finding's colour. Controllers currently match evidence strings back to raw logs manually.
4. **"Disagree with gold label" appendix** — after running the eval harness, document which label differences are genuine model mistakes vs. suspected labelling errors.
5. **Adversarial input handling** — normalise out-of-order timestamps, Unicode control characters in `reason_code`, tcode fields with whitespace or lowercase variants, and malformed ISO 8601 timestamps.
=======
5. **Adversarial input handling** — validate and normalise: out-of-order timestamps (sort before checks), `reason_code` with embedded Unicode control characters, `tcode` fields with leading/trailing whitespace or lowercase variants, and malformed ISO 8601 timestamps (e.g. without timezone marker). Currently any of these silently corrupt specific rule results.

---

## Hours log

See [HOURS.md](HOURS.md) for a full breakdown.

## Author

**Maciek Adamski** — [@madamski9](https://github.com/madamski9)

## License

This project is currently developed as part of an internship project at Seargin. License terms TBD.
