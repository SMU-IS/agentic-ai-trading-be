"""
LLM Pipeline Evaluation Script (Self-Contained in testing/)
Tests ticker identification, event identification, and sentiment analysis
INDEPENDENTLY across multiple LLMs using curated datasets with ground truth.

Each service is tested in isolation:
  - Ticker ID:  raw posts (no metadata) -> identify tickers -> compare vs ground truth
  - Event ID:   posts with correct tickers pre-populated -> identify events -> compare
  - Sentiment:  posts with correct tickers+events pre-populated -> classify sentiment -> compare

Data files are loaded from local testing/ directory (NOT S3) to ensure fair comparison.
Each LLM gets a fresh copy of alias_to_canonical and financial_event_types per run.

Usage:
    python evaluate_llms.py --prepare                          # Create all 3 datasets + batches
    python evaluate_llms.py --service ticker --llm gemini      # Test one service + one LLM
    python evaluate_llms.py --service ticker --all             # Test one service + all LLMs
    python evaluate_llms.py --service event --llm llama
    python evaluate_llms.py --service sentiment --llm deepseek
    python evaluate_llms.py --evaluate ticker                  # Generate results file from combined outputs
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
import copy
import logging
from pathlib import Path
from typing import Dict, List, Optional

# Setup path: add testing/ directory so local imports work
TESTING_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TESTING_DIR)

from config import env_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

GOLDEN_DATASET_NAME = "curated_dataset_200.json"
GOLDEN_DATASET_PATH = os.path.join(TESTING_DIR, GOLDEN_DATASET_NAME)

# Service directory mapping
SERVICE_DIRS = {
    "ticker": "ticker_identification",
    "event": "event_identification",
    "sentiment": "sentiment_analysis",
}

# Local data file paths (shared across LLMs, read-only)
CLEANED_TICKERS_PATH = os.path.join(TESTING_DIR, "ticker_identification", "cleaned_tickers.json")

BATCH_SIZE = 25
RANDOM_SEED = 42

RATE_LIMIT_DELAY = {
    "gemini": 4.0,
    "llama": 5.0,
    "deepseek": 3.0,
    "qwen": 5.0,
}

# Retry config for rate limit (429) and transient errors
MAX_RETRIES = 3
RETRY_BACKOFF = [10, 30, 60]  # seconds to wait per retry attempt

# Gemini fallback: switch to flash when pro hits rate limit
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"

LLM_CONFIGS = {
    "gemini": {
        "display_name": "Gemini 2.5 Pro",
        "folder_name": "Gemini",
        "model_name": "gemini-2.5-pro",
        "provider": "gemini",
    },
    "llama": {
        "display_name": "Llama 3.3 70B (Groq)",
        "folder_name": "Llama",
        "model_name": "llama-3.3-70b-versatile",
        "provider": "groq",
    },
    "deepseek": {
        "display_name": "DeepSeek R1 0528 (OpenRouter)",
        "folder_name": "DeepSeek",
        "model_name": "deepseek/deepseek-r1-0528",
        "provider": "deepseek",
    },
    "qwen": {
        "display_name": "Qwen3 32B (Groq)",
        "folder_name": "Qwen",
        "model_name": "qwen/qwen3-32b",
        "provider": "groq",
    },
}


# =============================================================================
# HELPER: PATHS
# =============================================================================

def get_service_dir(service: str) -> str:
    return os.path.join(TESTING_DIR, SERVICE_DIRS[service])


def get_batch_input_dir(service: str) -> str:
    return os.path.join(get_service_dir(service), "batch_input")


def get_batch_output_dir(service: str, llm_key: str = "") -> str:
    base = os.path.join(get_service_dir(service), "batch_output")
    if llm_key:
        path = os.path.join(base, LLM_CONFIGS[llm_key]["folder_name"])
        os.makedirs(path, exist_ok=True)
        return path
    return base


def get_results_path(service: str) -> str:
    return os.path.join(get_service_dir(service), f"{SERVICE_DIRS[service]}_results.json")


def get_alias_path(llm_key: str) -> str:
    """Get path to this LLM's alias_to_canonical.json (per-LLM copy)."""
    folder = LLM_CONFIGS[llm_key]["folder_name"]
    return os.path.join(TESTING_DIR, "ticker_identification", "batch_output", folder, "alias_to_canonical.json")


def get_event_types_path(llm_key: str) -> str:
    """Get path to this LLM's financial_event_types.json (per-LLM copy)."""
    folder = LLM_CONFIGS[llm_key]["folder_name"]
    return os.path.join(TESTING_DIR, "event_identification", "batch_output", folder, "financial_event_types.json")


# =============================================================================
# LOCAL DATA LOADING (no S3)
# =============================================================================

def _load_golden_dataset() -> List[Dict]:
    if not os.path.exists(GOLDEN_DATASET_PATH):
        print(f"ERROR: Golden dataset not found at {GOLDEN_DATASET_PATH}")
        sys.exit(1)
    with open(GOLDEN_DATASET_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_cleaned_tickers() -> dict:
    if not os.path.exists(CLEANED_TICKERS_PATH):
        print(f"ERROR: cleaned_tickers.json not found at {CLEANED_TICKERS_PATH}")
        sys.exit(1)
    with open(CLEANED_TICKERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_alias_to_canonical(llm_key: str) -> dict:
    """Load a fresh copy of alias_to_canonical for this LLM."""
    path = get_alias_path(llm_key)
    if not os.path.exists(path):
        print(f"ERROR: alias_to_canonical.json not found at {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_event_types(llm_key: str) -> dict:
    """Load a fresh copy of financial_event_types for this LLM."""
    path = get_event_types_path(llm_key)
    if not os.path.exists(path):
        print(f"ERROR: financial_event_types.json not found at {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_alias_to_canonical(llm_key: str, alias_data: dict):
    """Save updated alias_to_canonical after an LLM run."""
    path = get_alias_path(llm_key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(alias_data, f, indent=2, ensure_ascii=False)
    print(f"  Updated alias_to_canonical saved to: {path}")


def _save_event_types(llm_key: str, event_data: dict):
    """Save updated financial_event_types after an LLM run."""
    path = get_event_types_path(llm_key)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(event_data, f, indent=2, ensure_ascii=False)
    print(f"  Updated financial_event_types saved to: {path}")


def _build_ticker_to_title(cleaned_tickers: dict) -> dict:
    """Build a ticker symbol -> official name mapping from cleaned_tickers."""
    ticker_to_title = {}
    for _, data in cleaned_tickers.items():
        ticker_to_title[data["ticker"]] = data.get("title", data["ticker"])
    return ticker_to_title


# =============================================================================
# DATASET PREPARATION
# =============================================================================

def _save_batches(posts: List[Dict], output_dir: str, prefix: str = "batch") -> int:
    """Split posts into batches of BATCH_SIZE and save each as a JSON file."""
    total_batches = (len(posts) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_num in range(1, total_batches + 1):
        start = (batch_num - 1) * BATCH_SIZE
        end = start + BATCH_SIZE
        batch = posts[start:end]
        batch_file = os.path.join(output_dir, f"{prefix}_{batch_num}.json")
        with open(batch_file, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2, ensure_ascii=False)
    return total_batches


def prepare_datasets():
    """
    Create 3 testing datasets from the golden dataset:
      1. dataset_ticker.json  - No correct_metadata (200 posts, randomized)
      2. dataset_event.json   - ticker_metadata pre-populated with correct tickers (160 posts)
      3. dataset_sentiment.json - ticker_metadata pre-populated with correct tickers + events (160 posts)

    Also creates batch files for each dataset.
    """
    golden_posts = _load_golden_dataset()
    print(f"Loaded {len(golden_posts)} posts from {GOLDEN_DATASET_NAME}")

    cleaned_tickers = _load_cleaned_tickers()
    ticker_to_title = _build_ticker_to_title(cleaned_tickers)

    # Randomize order with fixed seed
    random.seed(RANDOM_SEED)
    shuffled_posts = copy.deepcopy(golden_posts)
    random.shuffle(shuffled_posts)

    # Separate posts with tickers vs "no ticker identified"
    posts_with_tickers = []
    posts_no_tickers = []
    for post in shuffled_posts:
        correct = post.get("correct_metadata", {})
        if "removed_reason" in correct:
            posts_no_tickers.append(post)
        else:
            posts_with_tickers.append(post)

    print(f"  Posts with tickers: {len(posts_with_tickers)}")
    print(f"  Posts without tickers: {len(posts_no_tickers)}")

    # -------------------------------------------------------------------------
    # Dataset 1: Ticker Identification (200 posts, no correct_metadata)
    # -------------------------------------------------------------------------
    dataset_ticker = []
    for post in shuffled_posts:
        clean_post = {k: v for k, v in post.items() if k != "correct_metadata"}
        dataset_ticker.append(clean_post)

    ticker_input_dir = get_batch_input_dir("ticker")
    dataset_ticker_path = os.path.join(ticker_input_dir, "dataset_ticker.json")
    with open(dataset_ticker_path, "w", encoding="utf-8") as f:
        json.dump(dataset_ticker, f, indent=2, ensure_ascii=False)

    num_batches = _save_batches(dataset_ticker, ticker_input_dir)
    print(f"\nDataset 1 (Ticker): {len(dataset_ticker)} posts, {num_batches} batches")
    print(f"  Saved to: {ticker_input_dir}")

    # -------------------------------------------------------------------------
    # Dataset 2: Event Identification (160 posts, ticker_metadata pre-populated)
    # -------------------------------------------------------------------------
    dataset_event = []
    for post in posts_with_tickers:
        event_post = {k: v for k, v in post.items() if k != "correct_metadata"}
        correct = post.get("correct_metadata", {})

        ticker_metadata = {}
        for ticker, meta in correct.items():
            if ticker == "removed_reason":
                continue
            ticker_metadata[ticker] = {
                "type": "stock",
                "official_name": ticker_to_title.get(ticker, ticker),
                "name_identified": [ticker],
            }

        event_post["ticker_metadata"] = ticker_metadata
        dataset_event.append(event_post)

    event_input_dir = get_batch_input_dir("event")
    dataset_event_path = os.path.join(event_input_dir, "dataset_event.json")
    with open(dataset_event_path, "w", encoding="utf-8") as f:
        json.dump(dataset_event, f, indent=2, ensure_ascii=False)

    num_batches = _save_batches(dataset_event, event_input_dir)
    print(f"\nDataset 2 (Event): {len(dataset_event)} posts, {num_batches} batches")
    print(f"  Saved to: {event_input_dir}")

    # -------------------------------------------------------------------------
    # Dataset 3: Sentiment Analysis (160 posts, ticker_metadata + events pre-populated)
    # -------------------------------------------------------------------------
    dataset_sentiment = []
    for post in posts_with_tickers:
        sent_post = {k: v for k, v in post.items() if k != "correct_metadata"}
        correct = post.get("correct_metadata", {})

        ticker_metadata = {}
        for ticker, meta in correct.items():
            if ticker == "removed_reason":
                continue
            ticker_metadata[ticker] = {
                "type": "stock",
                "official_name": ticker_to_title.get(ticker, ticker),
                "name_identified": [ticker],
                "event_type": meta.get("event_type"),
                "event_proposal": meta.get("event_proposal"),
            }

        sent_post["ticker_metadata"] = ticker_metadata
        dataset_sentiment.append(sent_post)

    sentiment_input_dir = get_batch_input_dir("sentiment")
    dataset_sentiment_path = os.path.join(sentiment_input_dir, "dataset_sentiment.json")
    with open(dataset_sentiment_path, "w", encoding="utf-8") as f:
        json.dump(dataset_sentiment, f, indent=2, ensure_ascii=False)

    num_batches = _save_batches(dataset_sentiment, sentiment_input_dir)
    print(f"\nDataset 3 (Sentiment): {len(dataset_sentiment)} posts, {num_batches} batches")
    print(f"  Saved to: {sentiment_input_dir}")

    print("\nAll datasets and batches prepared successfully.")


# =============================================================================
# LLM FACTORY
# =============================================================================

def create_llm(provider: str, model_name: str, temperature: float = 0, json_mode: bool = False):
    """Create a LangChain LLM based on provider."""
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=env_config.gemini_api_key,
            temperature=temperature,
        )
    elif provider == "groq":
        from langchain_groq import ChatGroq
        kwargs = {}
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return ChatGroq(
            model=model_name,
            api_key=env_config.groq_api_key,
            temperature=temperature,
            **kwargs,
        )
    elif provider == "deepseek":
        from langchain_openai import ChatOpenAI
        kwargs = {}
        if json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        api_key = env_config.openrouter_api_key
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set. Add it to your .env file.")
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=temperature,
            **kwargs,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")


# =============================================================================
# SERVICE WRAPPERS
# =============================================================================

class EvalTickerService:
    """Wrapper around TickerIdentificationService with swappable LLM."""

    def __init__(self, cleaned_tickers, alias_to_canonical, provider, model_name):
        # Import from local testing/ticker_identification/
        sys.path.insert(0, os.path.join(TESTING_DIR, "ticker_identification"))
        from _02_ticker_identification import TickerIdentificationService

        self.service = TickerIdentificationService(
            cleaned_tickers=cleaned_tickers,
            alias_to_canonical=alias_to_canonical,
        )
        llm = create_llm(provider, model_name, temperature=0)
        self.service._get_llm = lambda: llm

    def process_post(self, post: Dict) -> Dict:
        return self.service.process_post(post)


class EvalEventService:
    """Wrapper around EventIdentifierService with swappable LLM."""

    def __init__(self, event_list, provider, model_name):
        # Import from local testing/event_identification/
        sys.path.insert(0, os.path.join(TESTING_DIR, "event_identification"))
        from _03_event_identification import EventIdentifierService

        self.service = EventIdentifierService(
            event_list=event_list,
            testflag=True,
        )
        llm = create_llm(provider, model_name, temperature=0, json_mode=True)
        self.service._get_llm = lambda: llm

    def analyse_event(self, post: Dict) -> Dict:
        return self.service.analyse_event(post)


class EvalSentimentService:
    """Wrapper around sentiment analysis with swappable LLM."""

    def __init__(self, provider, model_name):
        # Import from local testing/sentiment_analysis/
        sys.path.insert(0, os.path.join(TESTING_DIR, "sentiment_analysis"))
        from _05_sentiment_prompts import build_sentiment_prompt
        from langchain_core.output_parsers import JsonOutputParser

        self.llm = create_llm(provider, model_name, temperature=0.1)
        self.parser = JsonOutputParser()
        self.build_sentiment_prompt = build_sentiment_prompt

    async def analyse(self, item: Dict) -> Dict:
        """Analyze sentiment per ticker using the LLM."""
        content = item.get("content", {})
        text = content.get("clean_combined_withurl", "")
        ticker_metadata = item.get("ticker_metadata", {})

        if not ticker_metadata or not text:
            return item

        if len(text) > 3000:
            text = text[:3000] + "..."

        tickers_info_lines = []
        for ticker, info in ticker_metadata.items():
            official_name = info.get("official_name", ticker)
            event_type = info.get("event_type", "Unknown")
            tickers_info_lines.append(f"- {ticker} ({official_name}) - Event: {event_type}")
        tickers_info = "\n".join(tickers_info_lines)

        try:
            from langchain_core.prompts import ChatPromptTemplate

            prompt_messages = self.build_sentiment_prompt(text, tickers_info)
            sentiment_prompt = ChatPromptTemplate.from_messages(prompt_messages)
            chain = sentiment_prompt | self.llm | self.parser
            result = await chain.ainvoke({})

            raw_sentiments = result.get("ticker_sentiments", {})
            for ticker in ticker_metadata:
                if ticker in raw_sentiments:
                    raw = raw_sentiments[ticker]
                    score = float(raw.get("sentiment_score", 0.0))
                    score = max(-1.0, min(1.0, score))
                    if score > 0.1:
                        label = "positive"
                    elif score < -0.1:
                        label = "negative"
                    else:
                        label = "neutral"
                    ticker_metadata[ticker]["sentiment_score"] = round(score, 4)
                    ticker_metadata[ticker]["sentiment_label"] = label
                    ticker_metadata[ticker]["sentiment_reasoning"] = raw.get("reasoning", "")
                else:
                    ticker_metadata[ticker]["sentiment_score"] = 0.0
                    ticker_metadata[ticker]["sentiment_label"] = "neutral"
                    ticker_metadata[ticker]["sentiment_reasoning"] = "Not in LLM response"

            item["ticker_metadata"] = ticker_metadata

        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            for ticker in ticker_metadata:
                ticker_metadata[ticker]["sentiment_score"] = 0.0
                ticker_metadata[ticker]["sentiment_label"] = "neutral"
                ticker_metadata[ticker]["sentiment_reasoning"] = f"Error: {str(e)[:100]}"

        return item


# =============================================================================
# RETRY HELPER
# =============================================================================

def _is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable (rate limit) vs permanent (auth/credits)."""
    error_str = str(error)
    # Retryable: 429 rate limit, 503 service unavailable, 529 overloaded
    if any(code in error_str for code in ["429", "503", "529", "rate limit", "Rate limit"]):
        return True
    # NOT retryable: 401 auth, 402 payment, 403 forbidden
    if any(code in error_str for code in ["401", "402", "403", "Payment Required", "Insufficient credits"]):
        return False
    # Default: retry on unknown errors
    return True


def _is_rate_limit_error(error: Exception) -> bool:
    """Check specifically for rate limit (429) errors."""
    error_str = str(error)
    return any(code in error_str for code in ["429", "rate limit", "Rate limit", "Resource has been exhausted"])


def _swap_gemini_to_fallback(svc, provider: str, current_model: str) -> str:
    """
    If provider is gemini and we haven't already switched, swap to the fallback model.
    Returns the new model name (or current if no swap).
    """
    if provider != "gemini" or current_model == GEMINI_FALLBACK_MODEL:
        return current_model

    logger.warning(f"    >>> GEMINI MODEL SWITCH: {current_model} -> {GEMINI_FALLBACK_MODEL} (rate limit hit)")
    fallback_llm = create_llm("gemini", GEMINI_FALLBACK_MODEL, temperature=0)

    # Update the LLM on the service depending on type
    if isinstance(svc, EvalTickerService):
        svc.service._get_llm = lambda: fallback_llm
    elif isinstance(svc, EvalEventService):
        svc.service._get_llm = lambda: fallback_llm
    elif isinstance(svc, EvalSentimentService):
        svc.llm = fallback_llm

    return GEMINI_FALLBACK_MODEL


# =============================================================================
# SERVICE RUNNERS
# =============================================================================

def run_ticker_test(posts: List[Dict], llm_key: str, ticker_service: EvalTickerService, delay: float) -> List[Dict]:
    """Run ticker identification on posts and return results."""
    config = LLM_CONFIGS[llm_key]
    provider = config["provider"]
    current_model = config["model_name"]
    results = []

    for i, post in enumerate(posts):
        post_id = post.get("id", "unknown")
        print(f"    [{i+1}/{len(posts)}] {post_id}")
        working_post = copy.deepcopy(post)

        for attempt in range(MAX_RETRIES + 1):
            try:
                working_post = ticker_service.process_post(working_post)
                time.sleep(delay)
                break
            except Exception as e:
                if attempt < MAX_RETRIES and _is_retryable_error(e):
                    # Try Gemini fallback on rate limit before waiting
                    if _is_rate_limit_error(e):
                        current_model = _swap_gemini_to_fallback(ticker_service, provider, current_model)
                    wait = RETRY_BACKOFF[attempt]
                    logger.warning(f"    Retry {attempt+1}/{MAX_RETRIES} for {post_id} in {wait}s: {str(e)[:80]}")
                    time.sleep(wait)
                    working_post = copy.deepcopy(post)  # reset before retry
                else:
                    logger.error(f"    Ticker ID failed for {post_id}: {e}")
                    working_post["ticker_metadata"] = {}
                    break

        # Build generated_metadata
        if not working_post.get("ticker_metadata"):
            working_post["generated_metadata"] = {"removed_reason": "No ticker identified"}
        else:
            generated = {}
            for ticker, meta in working_post["ticker_metadata"].items():
                generated[ticker] = {
                    "type": meta.get("type", "stock"),
                    "official_name": meta.get("official_name", ticker),
                }
            working_post["generated_metadata"] = generated

        results.append(working_post)
    return results


def run_event_test(posts: List[Dict], llm_key: str, event_service: EvalEventService, delay: float) -> List[Dict]:
    """Run event identification on posts (with pre-populated ticker_metadata)."""
    config = LLM_CONFIGS[llm_key]
    provider = config["provider"]
    current_model = config["model_name"]
    results = []

    for i, post in enumerate(posts):
        post_id = post.get("id", "unknown")
        print(f"    [{i+1}/{len(posts)}] {post_id}")
        working_post = copy.deepcopy(post)

        for attempt in range(MAX_RETRIES + 1):
            try:
                working_post = event_service.analyse_event(working_post)
                time.sleep(delay)
                break
            except Exception as e:
                if attempt < MAX_RETRIES and _is_retryable_error(e):
                    if _is_rate_limit_error(e):
                        current_model = _swap_gemini_to_fallback(event_service, provider, current_model)
                    wait = RETRY_BACKOFF[attempt]
                    logger.warning(f"    Retry {attempt+1}/{MAX_RETRIES} for {post_id} in {wait}s: {str(e)[:80]}")
                    time.sleep(wait)
                    working_post = copy.deepcopy(post)
                else:
                    logger.error(f"    Event ID failed for {post_id}: {e}")
                    break

        # Build generated_metadata with event info
        generated = {}
        for ticker, meta in working_post.get("ticker_metadata", {}).items():
            generated[ticker] = {
                "event_type": meta.get("event_type"),
                "event_proposal": meta.get("event_proposal"),
            }
        working_post["generated_metadata"] = generated
        results.append(working_post)
    return results


async def run_sentiment_test(posts: List[Dict], llm_key: str, sentiment_service: EvalSentimentService, delay: float) -> List[Dict]:
    """Run sentiment analysis on posts (with pre-populated ticker_metadata + events)."""
    config = LLM_CONFIGS[llm_key]
    provider = config["provider"]
    current_model = config["model_name"]
    results = []

    for i, post in enumerate(posts):
        post_id = post.get("id", "unknown")
        print(f"    [{i+1}/{len(posts)}] {post_id}")
        working_post = copy.deepcopy(post)

        for attempt in range(MAX_RETRIES + 1):
            try:
                working_post = await sentiment_service.analyse(working_post)
                time.sleep(delay)
                break
            except Exception as e:
                if attempt < MAX_RETRIES and _is_retryable_error(e):
                    if _is_rate_limit_error(e):
                        current_model = _swap_gemini_to_fallback(sentiment_service, provider, current_model)
                    wait = RETRY_BACKOFF[attempt]
                    logger.warning(f"    Retry {attempt+1}/{MAX_RETRIES} for {post_id} in {wait}s: {str(e)[:80]}")
                    time.sleep(wait)
                    working_post = copy.deepcopy(post)
                else:
                    logger.error(f"    Sentiment failed for {post_id}: {e}")
                    break

        # Build generated_metadata with sentiment info
        generated = {}
        for ticker, meta in working_post.get("ticker_metadata", {}).items():
            generated[ticker] = {
                "sentiment_label": meta.get("sentiment_label", "neutral"),
                "sentiment_score": meta.get("sentiment_score", 0.0),
                "sentiment_reasoning": meta.get("sentiment_reasoning", ""),
            }
        working_post["generated_metadata"] = generated
        results.append(working_post)
    return results


# =============================================================================
# BATCH PROCESSING ORCHESTRATOR
# =============================================================================

async def run_service_evaluation(service: str, llm_key: str):
    """Run a single service test for a single LLM across all batches."""
    config = LLM_CONFIGS[llm_key]
    provider = config["provider"]
    model_name = config["model_name"]
    folder_name = config["folder_name"]
    delay = RATE_LIMIT_DELAY.get(llm_key, 2.0)

    input_dir = get_batch_input_dir(service)
    output_dir = get_batch_output_dir(service, llm_key)

    # Find batch input files
    batch_files = sorted(
        [f for f in os.listdir(input_dir) if f.startswith("batch_") and f.endswith(".json")],
        key=lambda x: int(x.replace("batch_", "").replace(".json", "")),
    )

    if not batch_files:
        print(f"ERROR: No batch files found in {input_dir}. Run --prepare first.")
        return

    print(f"\n{'#' * 70}")
    print(f"  Service: {SERVICE_DIRS[service]}")
    print(f"  LLM: {config['display_name']} ({model_name})")
    print(f"  Batches: {len(batch_files)} | Rate limit delay: {delay}s")
    print(f"{'#' * 70}")

    # Load data from local files (fresh copy per LLM run for fairness)
    print("  Loading pipeline data from local files...")
    cleaned_tickers = _load_cleaned_tickers()

    # Initialize the appropriate service with per-LLM data copies
    if service == "ticker":
        alias_to_canonical = _load_alias_to_canonical(llm_key)
        print(f"  Loaded alias_to_canonical ({len(alias_to_canonical)} entries) for {folder_name}")
        svc = EvalTickerService(cleaned_tickers, alias_to_canonical, provider, model_name)
    elif service == "event":
        event_list = _load_event_types(llm_key)
        print(f"  Loaded financial_event_types ({len(event_list)} entries) for {folder_name}")
        svc = EvalEventService(event_list, provider, model_name)
    elif service == "sentiment":
        svc = EvalSentimentService(provider, model_name)

    start_time = time.time()
    all_results = []

    for bf in batch_files:
        batch_num = bf.replace("batch_", "").replace(".json", "")
        print(f"\n  --- Batch {batch_num}/{len(batch_files)} ---")

        with open(os.path.join(input_dir, bf), "r", encoding="utf-8") as f:
            batch_posts = json.load(f)

        # Run the appropriate service
        if service == "ticker":
            batch_results = run_ticker_test(batch_posts, llm_key, svc, delay)
        elif service == "event":
            batch_results = run_event_test(batch_posts, llm_key, svc, delay)
        elif service == "sentiment":
            batch_results = await run_sentiment_test(batch_posts, llm_key, svc, delay)

        # Save batch output
        out_file = os.path.join(output_dir, f"{service}_{folder_name}_batch_{batch_num}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(batch_results, f, indent=2, ensure_ascii=False)
        print(f"    Saved: {service}_{folder_name}_batch_{batch_num}.json")

        all_results.extend(batch_results)

    elapsed = time.time() - start_time
    print(f"\n  Completed in {elapsed:.1f}s ({elapsed/60:.1f} min)")

    # Save updated data files after the run (per Bryan's requirement)
    if service == "ticker":
        if svc.service.new_alias_count > 0:
            print(f"  [{folder_name}] {svc.service.new_alias_count} new aliases discovered")
            _save_alias_to_canonical(llm_key, svc.service.alias_to_canonical)
        else:
            print(f"  [{folder_name}] No new aliases discovered")
    elif service == "event":
        if svc.service.neweventcount > 0:
            print(f"  [{folder_name}] {svc.service.neweventcount} new event types proposed")
            _save_event_types(llm_key, svc.service.event_list)
        else:
            print(f"  [{folder_name}] No new event types proposed")

    # Combine all batches into one file
    combined_file = os.path.join(output_dir, f"{service}_{folder_name}_results.json")
    with open(combined_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"  Combined output: {combined_file}")
    print(f"  Total posts processed: {len(all_results)}")


# =============================================================================
# METRICS
# =============================================================================

def build_confusion_matrix(labels: List[str], predictions: List[str], classes: List[str]) -> Dict:
    """Build a confusion matrix and per-class precision/recall/F1."""
    matrix = {actual: {pred: 0 for pred in classes} for actual in classes}
    for actual, pred in zip(labels, predictions):
        if actual in matrix and pred in matrix[actual]:
            matrix[actual][pred] += 1

    per_class = {}
    for cls in classes:
        tp = matrix[cls][cls]
        fp = sum(matrix[other][cls] for other in classes if other != cls)
        fn = sum(matrix[cls][other] for other in classes if other != cls)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        per_class[cls] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": tp + fn,
        }

    return {"matrix": matrix, "per_class": per_class}


def evaluate_ticker(llm_key: str, golden_posts: List[Dict]) -> Dict:
    """Evaluate ticker identification results for one LLM."""
    output_dir = get_batch_output_dir("ticker", llm_key)
    folder_name = LLM_CONFIGS[llm_key]["folder_name"]
    combined_path = os.path.join(output_dir, f"ticker_{folder_name}_results.json")

    if not os.path.exists(combined_path):
        print(f"  WARNING: {combined_path} not found. Skipping {llm_key}.")
        return {}

    with open(combined_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    golden_map = {p["id"]: p.get("correct_metadata", {}) for p in golden_posts}

    precision_sum = 0.0
    recall_sum = 0.0
    f1_sum = 0.0
    count = 0
    no_ticker_tp = 0
    no_ticker_fp = 0
    no_ticker_fn = 0
    no_ticker_tn = 0
    post_details = []

    for post in results:
        post_id = post.get("id")
        correct = golden_map.get(post_id, {})
        generated = post.get("generated_metadata", {})

        gt_no_ticker = "removed_reason" in correct
        gen_no_ticker = "removed_reason" in generated

        if gt_no_ticker and gen_no_ticker:
            no_ticker_tp += 1
            post_details.append({"id": post_id, "result": "true_negative"})
            continue
        elif gt_no_ticker and not gen_no_ticker:
            no_ticker_fp += 1
            post_details.append({"id": post_id, "result": "false_positive", "spurious": list(generated.keys())})
            continue
        elif not gt_no_ticker and gen_no_ticker:
            no_ticker_fn += 1
            correct_tickers = [k for k in correct.keys() if k != "removed_reason"]
            post_details.append({"id": post_id, "result": "false_negative", "missed": correct_tickers})
            count += 1
            continue
        else:
            no_ticker_tn += 1

        gen_tickers = set(k for k in generated.keys() if k != "removed_reason")
        correct_tickers = set(k for k in correct.keys() if k != "removed_reason")

        tp = gen_tickers & correct_tickers
        fp = gen_tickers - correct_tickers
        fn = correct_tickers - gen_tickers

        p = len(tp) / len(gen_tickers) if gen_tickers else 0.0
        r = len(tp) / len(correct_tickers) if correct_tickers else 0.0
        f = (2 * p * r / (p + r)) if (p + r) > 0 else 0.0

        precision_sum += p
        recall_sum += r
        f1_sum += f
        count += 1

        post_details.append({
            "id": post_id,
            "result": "evaluated",
            "true_positives": list(tp),
            "false_positives": list(fp),
            "false_negatives": list(fn),
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f, 4),
        })

    n = count or 1
    total_no_ticker_gt = no_ticker_tp + no_ticker_fp
    no_ticker_accuracy = no_ticker_tp / total_no_ticker_gt if total_no_ticker_gt > 0 else 0.0

    return {
        "llm": LLM_CONFIGS[llm_key]["display_name"],
        "model": LLM_CONFIGS[llm_key]["model_name"],
        "total_posts": len(results),
        "posts_evaluated": count,
        "metrics": {
            "avg_precision": round(precision_sum / n, 4),
            "avg_recall": round(recall_sum / n, 4),
            "avg_f1": round(f1_sum / n, 4),
        },
        "no_ticker_detection": {
            "true_negative": no_ticker_tp,
            "false_positive": no_ticker_fp,
            "false_negative": no_ticker_fn,
            "true_positive": no_ticker_tn,
            "accuracy": round(no_ticker_accuracy, 4),
        },
        "post_details": post_details,
    }


def evaluate_event(llm_key: str, golden_posts: List[Dict]) -> Dict:
    """Evaluate event identification results for one LLM."""
    output_dir = get_batch_output_dir("event", llm_key)
    folder_name = LLM_CONFIGS[llm_key]["folder_name"]
    combined_path = os.path.join(output_dir, f"event_{folder_name}_results.json")

    if not os.path.exists(combined_path):
        print(f"  WARNING: {combined_path} not found. Skipping {llm_key}.")
        return {}

    with open(combined_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    golden_map = {p["id"]: p.get("correct_metadata", {}) for p in golden_posts}

    total = 0
    correct_count = 0
    event_labels_actual = []
    event_labels_pred = []
    post_details = []

    for post in results:
        post_id = post.get("id")
        correct = golden_map.get(post_id, {})
        generated = post.get("generated_metadata", {})

        details = []
        for ticker in set(correct.keys()) & set(generated.keys()):
            if ticker == "removed_reason":
                continue
            gt_event = correct[ticker].get("event_type")
            gen_event = generated[ticker].get("event_type")
            match = gt_event == gen_event
            if match:
                correct_count += 1
            total += 1
            if gt_event and gen_event:
                event_labels_actual.append(gt_event)
                event_labels_pred.append(gen_event)
            details.append({
                "ticker": ticker,
                "generated": gen_event,
                "correct": gt_event,
                "match": match,
            })

        post_details.append({"id": post_id, "details": details})

    accuracy = correct_count / total if total > 0 else 0.0

    all_event_types = sorted(set(event_labels_actual + event_labels_pred))
    confusion = build_confusion_matrix(event_labels_actual, event_labels_pred, all_event_types) if all_event_types else {"matrix": {}, "per_class": {}}

    # Macro-averaged metrics from confusion matrix
    per_class = confusion.get("per_class", {})
    if per_class:
        macro_precision = sum(v["precision"] for v in per_class.values()) / len(per_class)
        macro_recall = sum(v["recall"] for v in per_class.values()) / len(per_class)
        macro_f1 = sum(v["f1"] for v in per_class.values()) / len(per_class)
    else:
        macro_precision = macro_recall = macro_f1 = 0.0

    return {
        "llm": LLM_CONFIGS[llm_key]["display_name"],
        "model": LLM_CONFIGS[llm_key]["model_name"],
        "total_posts": len(results),
        "total_tickers_compared": total,
        "correct": correct_count,
        "metrics": {
            "accuracy": round(accuracy, 4),
            "macro_precision": round(macro_precision, 4),
            "macro_recall": round(macro_recall, 4),
            "macro_f1": round(macro_f1, 4),
        },
        "confusion_matrix": confusion,
        "post_details": post_details,
    }


def evaluate_sentiment(llm_key: str, golden_posts: List[Dict]) -> Dict:
    """Evaluate sentiment analysis results for one LLM."""
    output_dir = get_batch_output_dir("sentiment", llm_key)
    folder_name = LLM_CONFIGS[llm_key]["folder_name"]
    combined_path = os.path.join(output_dir, f"sentiment_{folder_name}_results.json")

    if not os.path.exists(combined_path):
        print(f"  WARNING: {combined_path} not found. Skipping {llm_key}.")
        return {}

    with open(combined_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    golden_map = {p["id"]: p.get("correct_metadata", {}) for p in golden_posts}

    total = 0
    correct_count = 0
    labels_actual = []
    labels_pred = []
    post_details = []

    for post in results:
        post_id = post.get("id")
        correct = golden_map.get(post_id, {})
        generated = post.get("generated_metadata", {})

        details = []
        for ticker in set(correct.keys()) & set(generated.keys()):
            if ticker == "removed_reason":
                continue
            gt_sentiment = correct[ticker].get("sentiment_label")
            gen_sentiment = generated[ticker].get("sentiment_label")
            match = gt_sentiment == gen_sentiment
            if match:
                correct_count += 1
            total += 1
            if gt_sentiment and gen_sentiment:
                labels_actual.append(gt_sentiment)
                labels_pred.append(gen_sentiment)
            details.append({
                "ticker": ticker,
                "generated": gen_sentiment,
                "correct": gt_sentiment,
                "match": match,
            })

        post_details.append({"id": post_id, "details": details})

    accuracy = correct_count / total if total > 0 else 0.0

    sentiment_classes = ["positive", "negative", "neutral"]
    confusion = build_confusion_matrix(labels_actual, labels_pred, sentiment_classes)

    per_class = confusion.get("per_class", {})
    if per_class:
        macro_precision = sum(v["precision"] for v in per_class.values()) / len(per_class)
        macro_recall = sum(v["recall"] for v in per_class.values()) / len(per_class)
        macro_f1 = sum(v["f1"] for v in per_class.values()) / len(per_class)
    else:
        macro_precision = macro_recall = macro_f1 = 0.0

    return {
        "llm": LLM_CONFIGS[llm_key]["display_name"],
        "model": LLM_CONFIGS[llm_key]["model_name"],
        "total_posts": len(results),
        "total_tickers_compared": total,
        "correct": correct_count,
        "metrics": {
            "accuracy": round(accuracy, 4),
            "macro_precision": round(macro_precision, 4),
            "macro_recall": round(macro_recall, 4),
            "macro_f1": round(macro_f1, 4),
        },
        "confusion_matrix": confusion,
        "post_details": post_details,
    }


def generate_results(service: str):
    """Generate the results file comparing all LLMs for a service."""
    golden_posts = _load_golden_dataset()

    evaluate_fn = {
        "ticker": evaluate_ticker,
        "event": evaluate_event,
        "sentiment": evaluate_sentiment,
    }[service]

    all_llm_results = {}
    for llm_key in LLM_CONFIGS:
        print(f"\n  Evaluating {llm_key}...")
        result = evaluate_fn(llm_key, golden_posts)
        if result:
            all_llm_results[llm_key] = result

    if not all_llm_results:
        print("  No results to evaluate.")
        return

    # Print comparison table
    print(f"\n{'=' * 80}")
    print(f"  {SERVICE_DIRS[service].upper()} - COMPARISON ACROSS LLMs")
    print(f"{'=' * 80}")

    if service == "ticker":
        print(f"\n  {'LLM':<35} {'Precision':>10} {'Recall':>10} {'F1':>10} {'No-Tick':>10}")
        print(f"  {'-' * 75}")
        for llm_key, data in all_llm_results.items():
            m = data["metrics"]
            nt = data["no_ticker_detection"]["accuracy"]
            print(f"  {data['llm']:<35} {m['avg_precision']:>9.2%} {m['avg_recall']:>9.2%} "
                  f"{m['avg_f1']:>9.2%} {nt:>9.2%}")
    elif service == "event":
        print(f"\n  {'LLM':<35} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10}")
        print(f"  {'-' * 75}")
        for llm_key, data in all_llm_results.items():
            m = data["metrics"]
            print(f"  {data['llm']:<35} {m['accuracy']:>9.2%} {m['macro_precision']:>9.2%} "
                  f"{m['macro_recall']:>9.2%} {m['macro_f1']:>9.2%}")
    elif service == "sentiment":
        print(f"\n  {'LLM':<35} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10}")
        print(f"  {'-' * 75}")
        for llm_key, data in all_llm_results.items():
            m = data["metrics"]
            print(f"  {data['llm']:<35} {m['accuracy']:>9.2%} {m['macro_precision']:>9.2%} "
                  f"{m['macro_recall']:>9.2%} {m['macro_f1']:>9.2%}")

        # Print per-class breakdown for each LLM
        for llm_key, data in all_llm_results.items():
            cm = data.get("confusion_matrix", {})
            per_class = cm.get("per_class", {})
            if per_class:
                print(f"\n  --- {data['llm']} Per-Class ---")
                print(f"  {'Label':<12} {'Precision':>10} {'Recall':>10} {'F1':>10} {'Support':>10}")
                print(f"  {'-' * 52}")
                for cls in ["positive", "negative", "neutral"]:
                    if cls in per_class:
                        pc = per_class[cls]
                        print(f"  {cls:<12} {pc['precision']:>9.2%} {pc['recall']:>9.2%} "
                              f"{pc['f1']:>9.2%} {pc['support']:>10}")

                matrix = cm.get("matrix", {})
                if matrix:
                    classes = ["positive", "negative", "neutral"]
                    print(f"\n  Confusion Matrix (rows=actual, cols=predicted):")
                    header = f"  {'':>12}" + "".join(f"{c:>12}" for c in classes)
                    print(header)
                    for actual in classes:
                        if actual in matrix:
                            row = f"  {actual:>12}" + "".join(f"{matrix[actual].get(pred, 0):>12}" for pred in classes)
                            print(row)

    print(f"\n{'=' * 80}")

    # Save results file (without post_details to keep it concise)
    results_path = get_results_path(service)
    save_data = {
        "service": SERVICE_DIRS[service],
        "golden_dataset": GOLDEN_DATASET_NAME,
    }
    for llm_key, data in all_llm_results.items():
        save_data[llm_key] = {k: v for k, v in data.items() if k != "post_details"}

    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {results_path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="LLM Pipeline Evaluation (Independent Services)")
    parser.add_argument(
        "--prepare", action="store_true",
        help="Prepare all 3 testing datasets and batch files",
    )
    parser.add_argument(
        "--service", type=str, choices=["ticker", "event", "sentiment"],
        help="Which service to test",
    )
    parser.add_argument(
        "--llm", type=str, choices=list(LLM_CONFIGS.keys()),
        help="Which LLM to test",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Test all LLMs for the specified service",
    )
    parser.add_argument(
        "--evaluate", type=str, choices=["ticker", "event", "sentiment"],
        help="Generate results file by comparing combined outputs against golden dataset",
    )

    args = parser.parse_args()

    if args.prepare:
        prepare_datasets()
        return

    if args.evaluate:
        generate_results(args.evaluate)
        return

    if args.service:
        llms_to_test = []
        if args.all:
            llms_to_test = list(LLM_CONFIGS.keys())
        elif args.llm:
            llms_to_test = [args.llm]
        else:
            print("ERROR: Specify --llm <name> or --all with --service")
            parser.print_help()
            sys.exit(1)

        for llm_key in llms_to_test:
            asyncio.run(run_service_evaluation(args.service, llm_key))

        return

    print("ERROR: Specify --prepare, --service, or --evaluate")
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
