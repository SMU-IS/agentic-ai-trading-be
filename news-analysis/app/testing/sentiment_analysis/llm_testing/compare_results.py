"""
Comparison Script: Evaluate Weight Combo Outputs Against Ground Truth
File: news-analysis/app/testing/sentiment_analysis/compare_results.py

After running evaluate_sentiment.py for all 5 combos, run this script to:
  1. Load all 5 output files from batch_output/Llama/
  2. Match each record against curated_dataset_200.json ground truth by ID
  3. Generate sentiment_Llama_mismatch_all.csv  — Excel-friendly, one row per (id, ticker)
  4. Generate sentiment_Llama_metrics.json      — accuracy metrics per combo
  5. Print accuracy table to console

Usage:
    python compare_results.py

Outputs (saved next to this script):
    sentiment_Llama_mismatch_all.csv   — all rows where ≥1 combo mismatched
    sentiment_Llama_metrics.json       — accuracy/class breakdown per combo

CSV columns:
    id | ticker | post_text_preview | ground_truth_label |
    combo1_label | combo2_label | combo3_label | combo4_label | combo5_label |
    combo1_match | combo2_match | combo3_match | combo4_match | combo5_match
"""

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Paths ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent                  # .../testing/sentiment_analysis/
TESTING_DIR = SCRIPT_DIR.parent                     # .../testing/

BATCH_OUTPUT_DIR = SCRIPT_DIR / "batch_output" / "Llama"
GROUND_TRUTH_PATH = TESTING_DIR / "curated_dataset_200.json"
MISMATCH_CSV_PATH = SCRIPT_DIR / "sentiment_Llama_mismatch_all.csv"
METRICS_JSON_PATH = SCRIPT_DIR / "sentiment_Llama_metrics.json"

# ── Combo metadata (for display) ──────────────────────────────────────────────
COMBO_NAMES: Dict[int, str] = {
    1: "Balanced       (0.25/0.25/0.25/0.25)",
    2: "Event-Driven   (0.50/0.25/0.10/0.15)",
    3: "Tone-Heavy     (0.30/0.40/0.10/0.20)",
    4: "Context-First  (0.30/0.20/0.10/0.40)",
    5: "Quality Aware  (0.30/0.25/0.25/0.20)",
}

COMBO_WEIGHTS: Dict[int, Dict[str, float]] = {
    1: {"market_impact": 0.25, "tone": 0.25, "source_quality": 0.25, "context": 0.25},
    2: {"market_impact": 0.50, "tone": 0.25, "source_quality": 0.10, "context": 0.15},
    3: {"market_impact": 0.30, "tone": 0.40, "source_quality": 0.10, "context": 0.20},
    4: {"market_impact": 0.30, "tone": 0.20, "source_quality": 0.10, "context": 0.40},
    5: {"market_impact": 0.30, "tone": 0.25, "source_quality": 0.25, "context": 0.20},
}


# ── File helpers ──────────────────────────────────────────────────────────────

def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Ground truth loader ───────────────────────────────────────────────────────

def build_ground_truth(path: Path) -> Dict[str, Dict[str, str]]:
    """
    Build a {post_id: {ticker: sentiment_label}} lookup from curated_dataset_200.json.
    Uses correct_metadata[ticker].sentiment_label as the ground truth.
    """
    curated = load_json(path)
    gt: Dict[str, Dict[str, str]] = {}
    for record in curated:
        record_id = record.get("id")
        correct_metadata = record.get("correct_metadata", {})
        if not record_id or not correct_metadata:
            continue
        gt[record_id] = {
            ticker: (data.get("sentiment_label") or "").lower()
            for ticker, data in correct_metadata.items()
            if isinstance(data, dict) and data.get("sentiment_label")
        }
    return gt


def build_post_text_lookup(path: Path) -> Dict[str, str]:
    """Build {post_id: text_preview} from curated_dataset_200.json for the CSV."""
    curated = load_json(path)
    lookup: Dict[str, str] = {}
    for record in curated:
        record_id = record.get("id")
        content = record.get("content", {})
        text = content.get("clean_combined_withurl", content.get("clean_combined_withouturl", ""))
        lookup[record_id] = (text[:200] + "...") if len(text) > 200 else text
    return lookup


# ── Combo output loader ───────────────────────────────────────────────────────

def load_combo_output(combo_num: int) -> Dict[str, Dict[str, str]]:
    """
    Load a combo output file.
    Returns {post_id: {ticker: sentiment_label}} from generated_metadata.
    """
    path = BATCH_OUTPUT_DIR / f"sentiment_Llama_combo{combo_num}.json"
    if not path.exists():
        print(f"  [WARNING] {path.name} not found — combo {combo_num} will show as N/A")
        return {}

    records = load_json(path)
    result: Dict[str, Dict[str, str]] = {}
    for record in records:
        record_id = record.get("id")
        generated = record.get("generated_metadata", {})
        if record_id:
            result[record_id] = {
                ticker: (data.get("sentiment_label") or "").lower()
                for ticker, data in generated.items()
            }
    return result


# ── Comparison builder ────────────────────────────────────────────────────────

def build_comparison_rows(
    ground_truth: Dict[str, Dict[str, str]],
    combo_outputs: Dict[int, Dict[str, Dict[str, str]]],
    post_text_lookup: Dict[str, str],
    available_combos: List[int],
) -> List[Dict]:
    """
    For every (post_id, ticker) pair present in ground truth, build one comparison row.
    Skips pairs where ALL available combos returned N/A (record not in any output).
    """
    rows: List[Dict] = []

    for post_id, gt_tickers in ground_truth.items():
        post_preview = post_text_lookup.get(post_id, "")

        for ticker, gt_label in gt_tickers.items():
            # Collect generated label for each combo
            generated: Dict[int, str] = {}
            for n in available_combos:
                lbl = combo_outputs[n].get(post_id, {}).get(ticker, "N/A")
                generated[n] = lbl

            # Skip entirely if no combo has a result for this pair
            if all(lbl == "N/A" for lbl in generated.values()):
                continue

            # Determine match flag per combo
            match: Dict[int, str] = {}
            for n in available_combos:
                if generated[n] == "N/A":
                    match[n] = "N/A"
                elif generated[n] == gt_label:
                    match[n] = "YES"
                else:
                    match[n] = "NO"

            row: Dict = {
                "id": post_id,
                "ticker": ticker,
                "post_text_preview": post_preview,
                "ground_truth_label": gt_label,
            }
            for n in range(1, 6):
                row[f"combo{n}_label"] = generated.get(n, "N/A")
            for n in range(1, 6):
                row[f"combo{n}_match"] = match.get(n, "N/A")

            rows.append(row)

    return rows


# ── Metrics calculator ────────────────────────────────────────────────────────

def compute_metrics(
    rows: List[Dict],
    available_combos: List[int],
) -> Dict:
    """Compute overall and per-class accuracy for each available combo."""
    metrics: Dict = {}

    for n in available_combos:
        match_col = f"combo{n}_match"
        scoreable = [r for r in rows if r[match_col] != "N/A"]
        correct = [r for r in scoreable if r[match_col] == "YES"]
        total = len(scoreable)
        accuracy = (len(correct) / total * 100) if total > 0 else 0.0

        by_class: Dict[str, Dict] = {}
        for label in ("positive", "negative", "neutral"):
            label_rows = [r for r in scoreable if r["ground_truth_label"] == label]
            label_correct = [r for r in label_rows if r[match_col] == "YES"]
            class_acc = (len(label_correct) / len(label_rows) * 100) if label_rows else 0.0
            by_class[label] = {
                "total": len(label_rows),
                "correct": len(label_correct),
                "accuracy_pct": round(class_acc, 2),
            }

        metrics[n] = {
            "combo_num": n,
            "name": COMBO_NAMES[n],
            "weights": COMBO_WEIGHTS[n],
            "total_pairs": total,
            "correct": len(correct),
            "accuracy_pct": round(accuracy, 2),
            "by_class": by_class,
        }

    return metrics


# ── Console display ───────────────────────────────────────────────────────────

def print_metrics_table(metrics: Dict, available_combos: List[int]) -> None:
    print("\n" + "=" * 72)
    print("  ACCURACY METRICS PER WEIGHT COMBINATION")
    print("=" * 72)

    for n in available_combos:
        m = metrics[n]
        print(f"\n  Combo {n}: {m['name']}")
        print(f"  {'Overall':10s} {m['correct']:>4}/{m['total_pairs']:<4}  =  {m['accuracy_pct']:5.1f}%")
        for label in ("positive", "negative", "neutral"):
            bc = m["by_class"][label]
            print(
                f"  {label.capitalize():10s} {bc['correct']:>4}/{bc['total']:<4}  =  {bc['accuracy_pct']:5.1f}%"
            )

    print("\n" + "=" * 72)

    # Best combo
    best_num = max(available_combos, key=lambda n: metrics[n]["accuracy_pct"])
    best = metrics[best_num]
    print(f"  BEST COMBO: {best_num} — {best['name']}")
    print(f"  Accuracy:   {best['accuracy_pct']}%  ({best['correct']}/{best['total_pairs']} correct)")
    print("=" * 72 + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 72)
    print("  SENTIMENT WEIGHT COMPARISON — Llama 3.3 70B")
    print("=" * 72)

    # Ground truth
    if not GROUND_TRUTH_PATH.exists():
        print(f"[ERROR] Ground truth file not found: {GROUND_TRUTH_PATH}")
        sys.exit(1)

    print(f"\n[INFO] Loading ground truth from {GROUND_TRUTH_PATH.name} ...")
    ground_truth = build_ground_truth(GROUND_TRUTH_PATH)
    post_text_lookup = build_post_text_lookup(GROUND_TRUTH_PATH)
    gt_pair_count = sum(len(tickers) for tickers in ground_truth.values())
    print(f"[INFO] {len(ground_truth)} posts  |  {gt_pair_count} (post, ticker) pairs with ground truth")

    # Load combo outputs
    print()
    combo_outputs: Dict[int, Dict] = {}
    available_combos: List[int] = []
    for n in range(1, 6):
        output = load_combo_output(n)
        combo_outputs[n] = output
        if output:
            available_combos.append(n)
            pair_count = sum(len(tickers) for tickers in output.values())
            print(f"[INFO] Combo {n}: {len(output)} posts  |  {pair_count} ticker results loaded")

    if not available_combos:
        print("\n[ERROR] No combo output files found. Run evaluate_sentiment.py first.")
        sys.exit(1)

    # Build comparison rows
    print(f"\n[INFO] Building comparison rows for {len(available_combos)} available combos ...")
    all_rows = build_comparison_rows(ground_truth, combo_outputs, post_text_lookup, available_combos)
    mismatch_rows = [
        row for row in all_rows
        if any(row[f"combo{n}_match"] == "NO" for n in available_combos)
    ]
    print(f"[INFO] Total comparable (post, ticker) pairs : {len(all_rows)}")
    print(f"[INFO] Pairs with ≥1 mismatch across combos  : {len(mismatch_rows)}")

    # Write mismatch CSV (Excel-friendly)
    csv_columns = [
        "id",
        "ticker",
        "post_text_preview",
        "ground_truth_label",
        "combo1_label",
        "combo2_label",
        "combo3_label",
        "combo4_label",
        "combo5_label",
        "combo1_match",
        "combo2_match",
        "combo3_match",
        "combo4_match",
        "combo5_match",
    ]

    with open(MISMATCH_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        # utf-8-sig adds BOM so Excel opens it correctly without garbling
        writer = csv.DictWriter(f, fieldnames=csv_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(mismatch_rows)

    print(f"\n[SAVED] Mismatch CSV  → {MISMATCH_CSV_PATH.name}  ({len(mismatch_rows)} rows)")

    # Compute and save metrics
    metrics = compute_metrics(all_rows, available_combos)
    save_json(METRICS_JSON_PATH, metrics)
    print(f"[SAVED] Metrics JSON  → {METRICS_JSON_PATH.name}")

    # Print summary table
    print_metrics_table(metrics, available_combos)


if __name__ == "__main__":
    main()
