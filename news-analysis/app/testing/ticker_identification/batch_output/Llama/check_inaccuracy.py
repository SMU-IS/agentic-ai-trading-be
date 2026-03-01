import json
from pathlib import Path
import sys
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent

INPUT_FILE = BASE_DIR / "ticker_Llama_results.json"
OUTPUT_FILE = BASE_DIR / "ticker_mismatch_output.json"
GOLDEN_DATASET_PATH = BASE_DIR / "curated_dataset_200.json"


def load_json(path):
    if not path.exists():
        print(f"ERROR: File not found -> {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_ticker_keys(metadata: dict):
    if not isinstance(metadata, dict):
        return set()
    if "removed_reason" in metadata:
        return set()
    return set(metadata.keys())


def main():
    print("Starting validation...")

    golden_posts = load_json(GOLDEN_DATASET_PATH)
    golden_map = {p["id"]: p.get("correct_metadata", {}) for p in golden_posts}

    model_posts = load_json(INPUT_FILE)

    problematic_posts = []

    for post in model_posts:
        post_id = post.get("id")

        generated_metadata = post.get("generated_metadata", {})
        correct_metadata = golden_map.get(post_id, {})

        generated_keys = extract_ticker_keys(generated_metadata)
        correct_keys = extract_ticker_keys(correct_metadata)

        golden_removed = correct_metadata.get("removed_reason")
        model_removed = generated_metadata.get("removed_reason")

        # -----------------------------------------
        # Case 1: Golden says no ticker, model generated tickers
        # -----------------------------------------
        if golden_removed == "No ticker identified" and generated_keys:
            post["_validation_error"] = {
                "reason": "Model hallucinated tickers",
                "correct_metadata": correct_metadata,
                "generated_metadata": generated_metadata,
            }
            problematic_posts.append(post)
            continue

        # -----------------------------------------
        # Case 2: Golden has tickers, model says no ticker
        # -----------------------------------------
        if correct_keys and model_removed == "No ticker identified":
            post["_validation_error"] = {
                "reason": "Model missed tickers",
                "correct_keys": sorted(correct_keys),
                "generated_keys": sorted(generated_keys),
            }
            problematic_posts.append(post)
            continue

        # -----------------------------------------
        # Case 3: Both have tickers but mismatch
        # -----------------------------------------
        if correct_keys != generated_keys:
            post["_validation_error"] = {
                "reason": "Ticker mismatch",
                "correct_keys": sorted(correct_keys),
                "generated_keys": sorted(generated_keys),
            }
            problematic_posts.append(post)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(problematic_posts, f, indent=2)

    print(f"Done. {len(problematic_posts)} mismatches written.")


if __name__ == "__main__":
    main()
