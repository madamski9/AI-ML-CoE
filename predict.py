"""
Batch prediction script for SAP Firefighter Log Compliance Reviewer.

Processes all session JSON files in a directory and writes predictions to a JSONL file.

Usage:
    # Generate predictions for training set:
    python predict.py --input dataset_candidate/train/sessions --output predictions_train.jsonl

    # Generate predictions for test set:
    python predict.py --input dataset_candidate/test/sessions --output predictions_test.jsonl

    # Generate predictions AND immediately evaluate against gold labels:
    python predict.py --input dataset_candidate/train/sessions --output predictions_train.jsonl \
        --eval dataset_candidate/train/labels.jsonl

    # Single file:
    python predict.py --input dataset_candidate/train/sessions/FF-TRAIN-0001.json --output out.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from ffreviewer.engine import review_session
from ffreviewer.models import Session


def process_file(path: Path) -> dict:
    session = Session.model_validate_json(path.read_text(encoding="utf-8"))
    verdict = review_session(session)
    return verdict.model_dump(mode="json")


def iter_session_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    files = sorted(input_path.glob("*.json"))
    if not files:
        raise SystemExit(f"No .json files found in {input_path}")
    return files


def run_eval(predictions_path: Path, labels_path: Path) -> None:
    import subprocess
    eval_script = Path(__file__).parent / "dataset_candidate" / "eval.py"
    result = subprocess.run(
        [sys.executable, str(eval_script),
         "--predictions", str(predictions_path),
         "--labels", str(labels_path)],
        check=False,
    )
    sys.exit(result.returncode)


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch predict FF session verdicts")
    ap.add_argument("--input", required=True,
                    help="Directory of session JSON files, or a single JSON file")
    ap.add_argument("--output", required=True,
                    help="Output JSONL file path for predictions")
    ap.add_argument("--eval", metavar="LABELS",
                    help="Gold labels JSONL — if provided, run eval.py after prediction")
    ap.add_argument("--skip-errors", action="store_true",
                    help="Continue on parse/review errors instead of aborting")
    args = ap.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise SystemExit(f"Input path does not exist: {input_path}")

    files = iter_session_files(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    errors = 0
    t0 = time.perf_counter()

    with output_path.open("w", encoding="utf-8") as out:
        for i, path in enumerate(files, 1):
            prefix = f"[{i:>3}/{len(files)}]"
            try:
                result = process_file(path)
                out.write(json.dumps(result) + "\n")
                out.flush()
                print(f"{prefix} {path.name:35s}  {result['verdict']}", flush=True)
            except Exception as exc:
                errors += 1
                msg = f"{prefix} {path.name:35s}  ERROR: {exc}"
                print(msg, file=sys.stderr, flush=True)
                if not args.skip_errors:
                    raise SystemExit(f"\nAborted. Use --skip-errors to continue past failures.") from exc

    elapsed = time.perf_counter() - t0
    ok = len(files) - errors
    print(f"\nDone: {ok}/{len(files)} sessions in {elapsed:.1f}s "
          f"({elapsed / len(files):.1f}s/session). "
          f"Predictions written to {output_path}")

    if errors:
        print(f"WARNING: {errors} session(s) failed — omitted from output.", file=sys.stderr)

    if args.eval:
        print(f"\nRunning eval against {args.eval} …\n")
        run_eval(output_path, Path(args.eval))


if __name__ == "__main__":
    main()
