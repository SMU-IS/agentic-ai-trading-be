"""
Unit Tests — LLMSentimentService
File: app/tests/test_sentiment_service.py

Run from sentiment-analysis-service/:
    pytest

Merged best-of-both: original tests + additional edge/sad/happy path coverage
for prompt building, fallback generation, ticker formatting, singleton,
dataclass, constants, and deeper _extract_json / _repair_truncated_json cases.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services._05_sentiment import (
    LLMSentimentService,
    LLMSentimentResult,
    FACTOR_WEIGHTS,
    MAX_TEXT_CHARS,
    MAX_TICKERS_PER_CALL,
    MAX_RETRIES,
    FALLBACK_REASONING,
    FALLBACK_FACTORS,
)
from app.services._05_sentiment_prompts import (
    build_sentiment_prompt,
    FEW_SHOT_EXAMPLES,
    SYSTEM_PROMPT,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

ALL_POSITIVE_FACTORS = {
    "market_impact": 0.8,
    "tone": 0.9,
    "source_quality": 0.7,
    "context": 0.8,
}

ALL_NEGATIVE_FACTORS = {
    "market_impact": -0.7,
    "tone": -0.8,
    "source_quality": -0.5,
    "context": -0.6,
}


def llm_response(ticker_sentiments: dict) -> dict:
    return {"ticker_sentiments": ticker_sentiments}


def sentiment_result(ticker: str, score: float, label: str, name: str) -> LLMSentimentResult:
    return LLMSentimentResult(
        ticker_sentiments={
            ticker: {
                "sentiment_score": score,
                "sentiment_label": label,
                "reasoning": "Test reasoning.",
                "factor_breakdown": ALL_POSITIVE_FACTORS if score > 0 else ALL_NEGATIVE_FACTORS,
                "official_name": name,
            }
        },
        analysis_successful=True,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset singleton before and after every test for isolation."""
    LLMSentimentService._instance = None
    yield
    LLMSentimentService._instance = None


@pytest.fixture
def service():
    """Fresh LLMSentimentService with mocked Groq LLM."""
    with patch("app.services._05_sentiment.ChatGroq") as mock_groq_cls:
        mock_llm = MagicMock()
        mock_groq_cls.return_value = mock_llm
        svc = LLMSentimentService()
        svc.llm = mock_llm
        svc.parser = MagicMock()
        yield svc

# ═══════════════════════════════════════════════════════════════════════════════
# 1. analyse() — happy path
# ═══════════════════════════════════════════════════════════════════════════════

async def test_analyse_single_ticker_positive(service):
    """Single ticker → positive sentiment returned and ticker_metadata enriched."""
    service._analyze_tickers = AsyncMock(
        return_value=sentiment_result("AAPL", 0.82, "positive", "Apple Inc.")
    )

    item = {
        "id": "post_001",
        "content": {"clean_combined_withurl": "Apple crushes Q4 earnings! 🚀"},
        "ticker_metadata": {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}},
    }

    result = await service.analyse(item)

    sa = result["sentiment_analysis"]
    assert sa["analysis_successful"] is True
    assert sa["ticker_sentiments"]["AAPL"]["sentiment_label"] == "positive"
    # ticker_metadata should be enriched with sentiment fields
    assert result["ticker_metadata"]["AAPL"]["sentiment_score"] == 0.82
    assert result["ticker_metadata"]["AAPL"]["sentiment_label"] == "positive"
    assert "sentiment_reasoning" in result["ticker_metadata"]["AAPL"]
    assert "factor_breakdown" in result["ticker_metadata"]["AAPL"]


async def test_analyse_multi_ticker_different_sentiments(service):
    """AAPL positive, MSFT negative — each ticker gets the correct label."""
    service._analyze_tickers = AsyncMock(
        return_value=LLMSentimentResult(
            ticker_sentiments={
                "AAPL": {
                    "sentiment_score": 0.75,
                    "sentiment_label": "positive",
                    "reasoning": "Crushed earnings.",
                    "factor_breakdown": ALL_POSITIVE_FACTORS,
                    "official_name": "Apple Inc.",
                },
                "MSFT": {
                    "sentiment_score": -0.55,
                    "sentiment_label": "negative",
                    "reasoning": "Cloud growth slowed.",
                    "factor_breakdown": ALL_NEGATIVE_FACTORS,
                    "official_name": "Microsoft Corporation",
                },
            },
            analysis_successful=True,
        )
    )

    item = {
        "id": "post_002",
        "content": {"clean_combined_withurl": "AAPL up, MSFT down after earnings."},
        "ticker_metadata": {
            "AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"},
            "MSFT": {"OfficialName": "Microsoft Corporation", "event_type": "EARNINGS"},
        },
    }

    result = await service.analyse(item)

    assert result["ticker_metadata"]["AAPL"]["sentiment_label"] == "positive"
    assert result["ticker_metadata"]["MSFT"]["sentiment_label"] == "negative"


async def test_analyse_neutral_content(service):
    """Factual/neutral content → neutral label returned."""
    service._analyze_tickers = AsyncMock(
        return_value=sentiment_result("TSLA", 0.05, "neutral", "Tesla Inc.")
    )

    item = {
        "id": "post_003",
        "content": {"clean_combined_withurl": "Tesla will hold its AGM on May 15th."},
        "ticker_metadata": {"TSLA": {"OfficialName": "Tesla Inc.", "event_type": "ANNOUNCEMENT"}},
    }

    result = await service.analyse(item)

    assert result["sentiment_analysis"]["ticker_sentiments"]["TSLA"]["sentiment_label"] == "neutral"


async def test_analyse_error_field_absent_on_success(service):
    """No 'error' key in sentiment_analysis when analysis succeeds."""
    service._analyze_tickers = AsyncMock(
        return_value=sentiment_result("AAPL", 0.5, "positive", "Apple Inc.")
    )

    item = {
        "content": {"clean_combined_withurl": "AAPL looks great"},
        "ticker_metadata": {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}},
    }

    result = await service.analyse(item)

    assert "error" not in result["sentiment_analysis"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. analyse() — sad path
# ═══════════════════════════════════════════════════════════════════════════════

async def test_analyse_empty_ticker_metadata_returns_error(service):
    """No ticker_metadata → error key in sentiment_analysis, no LLM call made."""
    item = {
        "id": "post_004",
        "content": {"clean_combined_withurl": "Some market news."},
        "ticker_metadata": {},
    }

    result = await service.analyse(item)

    assert "error" in result["sentiment_analysis"]
    assert result["sentiment_analysis"]["ticker_sentiments"] == {}


async def test_analyse_missing_ticker_metadata_key_returns_error(service):
    """Item missing ticker_metadata key entirely → error response."""
    item = {"content": {"clean_combined_withurl": "some text"}}

    result = await service.analyse(item)

    assert "error" in result["sentiment_analysis"]


async def test_analyse_empty_text_returns_fallback_sentiments(service):
    """Whitespace-only text → error returned with neutral fallback for each ticker."""
    item = {
        "id": "post_005",
        "content": {"clean_combined_withurl": "   "},
        "ticker_metadata": {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}},
    }

    result = await service.analyse(item)

    assert "error" in result["sentiment_analysis"]
    fallback = result["sentiment_analysis"]["ticker_sentiments"]["AAPL"]
    assert fallback["sentiment_label"] == "neutral"
    assert fallback["sentiment_score"] == 0.0


async def test_analyse_empty_string_text_returns_fallback(service):
    """Empty string (not just whitespace) → fallback sentiments."""
    item = {
        "content": {"clean_combined_withurl": ""},
        "ticker_metadata": {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}},
    }

    result = await service.analyse(item)

    assert result["sentiment_analysis"]["error"] == "Empty content"


async def test_analyse_missing_content_key_returns_fallback(service):
    """Missing 'content' key entirely → empty text → fallback."""
    item = {"ticker_metadata": {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}}}

    result = await service.analyse(item)

    assert result["sentiment_analysis"]["error"] == "Empty content"


async def test_analyse_llm_not_initialized_returns_fallback(service):
    """LLM is None (failed init) → fallback neutral for all tickers."""
    service.llm = None

    item = {
        "id": "post_006",
        "content": {"clean_combined_withurl": "Breaking market news."},
        "ticker_metadata": {"NVDA": {"OfficialName": "NVIDIA Corporation", "event_type": "EARNINGS"}},
    }

    result = await service._analyze_tickers("Breaking market news.", item["ticker_metadata"])

    assert result.analysis_successful is False
    assert result.error_message == "LLM not initialized"
    assert result.ticker_sentiments["NVDA"]["sentiment_label"] == "neutral"
    assert result.ticker_sentiments["NVDA"]["reasoning"] == FALLBACK_REASONING


async def test_analyse_failed_analysis_includes_error_key(service):
    """Failed LLM analysis includes error message in output."""
    mock_chain = AsyncMock()
    mock_chain.ainvoke = AsyncMock(side_effect=Exception("LLM down"))
    service.llm.__or__ = MagicMock(return_value=mock_chain)
    service._try_recover_partial = AsyncMock(return_value=None)

    item = {
        "content": {"clean_combined_withurl": "AAPL news"},
        "ticker_metadata": {
            "AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"},
        },
    }

    result = await service.analyse(item)

    sa = result["sentiment_analysis"]
    assert sa["analysis_successful"] is False
    assert "error" in sa


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _parse_response() — score computation, labels, fallbacks
# ═══════════════════════════════════════════════════════════════════════════════

def test_parse_response_computes_score_from_factors(service):
    """Valid LLM response with factor_breakdown → score computed from weights."""
    response = llm_response({
        "AAPL": {
            "factor_breakdown": ALL_POSITIVE_FACTORS,
            "reasoning": "Strong Q4 beat.",
        }
    })

    result = service._parse_response(response, {"AAPL": {"OfficialName": "Apple Inc."}})

    assert result["AAPL"]["sentiment_label"] == "positive"
    assert result["AAPL"]["sentiment_score"] > 0.1
    assert result["AAPL"]["official_name"] == "Apple Inc."
    assert result["AAPL"]["reasoning"] == "Strong Q4 beat."


def test_parse_response_score_recomputed_not_trusted_from_llm(service):
    """Server recomputes score from factors — LLM's score field is overridden."""
    response = llm_response({
        "AAPL": {
            "sentiment_score": 0.99,  # LLM claims 0.99
            "factor_breakdown": {
                "market_impact": 0.5, "tone": 0.5,
                "source_quality": 0.5, "context": 0.5,
            },
            "reasoning": "test",
        }
    })

    result = service._parse_response(response, {"AAPL": {"OfficialName": "Apple Inc."}})
    expected = round((0.5 * 0.3) + (0.5 * 0.4) + (0.5 * 0.1) + (0.5 * 0.2), 4)

    assert result["AAPL"]["sentiment_score"] == expected


def test_parse_response_missing_ticker_gets_fallback(service):
    """Ticker absent from LLM response → neutral fallback with zero score."""
    response = llm_response({})  # AAPL not in response

    result = service._parse_response(response, {"AAPL": {"OfficialName": "Apple Inc."}})

    assert result["AAPL"]["sentiment_score"] == 0.0
    assert result["AAPL"]["sentiment_label"] == "neutral"
    assert result["AAPL"]["reasoning"] == FALLBACK_REASONING


def test_parse_response_multiple_tickers_partial_missing(service):
    """Multiple tickers in metadata, only some in LLM response → missing get fallback."""
    response = llm_response({
        "AAPL": {
            "factor_breakdown": {"market_impact": 0.5, "tone": 0.5, "source_quality": 0.5, "context": 0.5},
            "reasoning": "Bullish.",
        }
        # MSFT and GOOGL missing
    })

    metadata = {
        "AAPL": {"OfficialName": "Apple Inc."},
        "MSFT": {"OfficialName": "Microsoft Corporation"},
        "GOOGL": {"OfficialName": "Alphabet Inc."},
    }

    result = service._parse_response(response, metadata)

    assert result["AAPL"]["sentiment_label"] == "positive"
    assert result["MSFT"]["reasoning"] == FALLBACK_REASONING
    assert result["MSFT"]["sentiment_score"] == 0.0
    assert result["GOOGL"]["reasoning"] == FALLBACK_REASONING


def test_parse_response_uses_llm_score_when_factors_all_zero(service):
    """All-zero factors → falls back to LLM-provided sentiment_score."""
    response = llm_response({
        "TSLA": {
            "sentiment_score": 0.65,
            "factor_breakdown": {k: 0.0 for k in FACTOR_WEIGHTS},
            "reasoning": "Generally bullish overall.",
        }
    })

    result = service._parse_response(response, {"TSLA": {"OfficialName": "Tesla Inc."}})

    assert result["TSLA"]["sentiment_score"] == 0.65
    assert result["TSLA"]["sentiment_label"] == "positive"


def test_parse_response_clamps_llm_score_to_valid_range(service):
    """LLM-provided score outside [-1, 1] is clamped."""
    response = llm_response({
        "GME": {
            "sentiment_score": 99.0,
            "factor_breakdown": {k: 0.0 for k in FACTOR_WEIGHTS},
            "reasoning": "Extreme case.",
        }
    })

    result = service._parse_response(response, {"GME": {"OfficialName": "GameStop Corp."}})

    assert result["GME"]["sentiment_score"] == 1.0


def test_parse_response_clamps_negative_llm_score(service):
    """LLM-provided score below -1.0 is clamped to -1.0."""
    response = llm_response({
        "GME": {
            "sentiment_score": -50.0,
            "factor_breakdown": {k: 0.0 for k in FACTOR_WEIGHTS},
            "reasoning": "Extreme negative.",
        }
    })

    result = service._parse_response(response, {"GME": {"OfficialName": "GameStop Corp."}})

    assert result["GME"]["sentiment_score"] == -1.0


def test_parse_response_missing_reasoning_gets_default(service):
    """Missing reasoning key → 'No reasoning provided'."""
    response = llm_response({
        "AAPL": {
            "factor_breakdown": {"market_impact": 0.3, "tone": 0.3, "source_quality": 0.0, "context": 0.0},
        }
    })

    result = service._parse_response(response, {"AAPL": {"OfficialName": "Apple Inc."}})

    assert result["AAPL"]["reasoning"] == "No reasoning provided"


def test_parse_response_empty_ticker_sentiments_dict(service):
    """LLM returns empty ticker_sentiments → all tickers get fallback."""
    response = {"ticker_sentiments": {}}

    result = service._parse_response(response, {"AAPL": {"OfficialName": "Apple Inc."}})

    assert result["AAPL"]["reasoning"] == FALLBACK_REASONING


def test_parse_response_missing_factor_breakdown_key(service):
    """No factor_breakdown key at all → factors default to zeros → uses LLM score."""
    response = llm_response({
        "AAPL": {
            "sentiment_score": 0.4,
            "reasoning": "test",
        }
    })

    result = service._parse_response(response, {"AAPL": {"OfficialName": "Apple Inc."}})

    # All factors 0 → falls back to LLM score
    assert result["AAPL"]["sentiment_score"] == 0.4


# ═══════════════════════════════════════════════════════════════════════════════
# 4. _parse_factors() — validation and clamping
# ═══════════════════════════════════════════════════════════════════════════════

def test_parse_factors_valid_values_pass_through(service):
    """Valid factors within [-1, 1] are returned unchanged."""
    raw = {"market_impact": 0.5, "tone": 0.7, "source_quality": 0.3, "context": 0.6}

    result = service._parse_factors(raw)

    assert result["market_impact"] == 0.5
    assert result["tone"] == 0.7
    assert result["source_quality"] == 0.3
    assert result["context"] == 0.6


def test_parse_factors_rounded_to_4_decimals(service):
    """Factors are rounded to 4 decimal places."""
    raw = {"market_impact": 0.123456789, "tone": 0.0, "source_quality": 0.0, "context": 0.0}

    result = service._parse_factors(raw)

    assert result["market_impact"] == 0.1235


def test_parse_factors_clamps_above_1(service):
    """Factors > 1.0 are clamped to 1.0."""
    raw = {"market_impact": 2.5, "tone": 1.5, "source_quality": 0.3, "context": 0.6}

    result = service._parse_factors(raw)

    assert result["market_impact"] == 1.0
    assert result["tone"] == 1.0


def test_parse_factors_clamps_below_minus_1(service):
    """Factors < -1.0 are clamped to -1.0."""
    raw = {"market_impact": -3.0, "tone": -0.5, "source_quality": 0.3, "context": -2.0}

    result = service._parse_factors(raw)

    assert result["market_impact"] == -1.0
    assert result["context"] == -1.0


def test_parse_factors_non_numeric_defaults_to_zero(service):
    """Non-numeric factor values (string, None) default to 0.0."""
    raw = {"market_impact": "strong", "tone": None, "source_quality": 0.3, "context": 0.6}

    result = service._parse_factors(raw)

    assert result["market_impact"] == 0.0
    assert result["tone"] == 0.0


def test_parse_factors_missing_keys_default_to_zero(service):
    """Missing factor keys default to 0.0."""
    result = service._parse_factors({})

    for key in FACTOR_WEIGHTS:
        assert result[key] == 0.0


def test_parse_factors_string_numbers_cast_to_float(service):
    """String-encoded numbers like '0.5' are cast to float."""
    raw = {"market_impact": "0.5", "tone": "-0.3", "source_quality": "0", "context": "0.0"}

    result = service._parse_factors(raw)

    assert result["market_impact"] == 0.5
    assert result["tone"] == -0.3


def test_parse_factors_extra_keys_ignored(service):
    """Extra unknown keys in raw factors are ignored — only 4 factors returned."""
    raw = {"market_impact": 0.5, "tone": 0.3, "source_quality": 0.1, "context": 0.2, "bogus": 99.9}

    result = service._parse_factors(raw)

    assert "bogus" not in result
    assert len(result) == 4


def test_parse_factors_empty_dict_returns_all_zeros(service):
    """Empty dict → all factors are 0.0 with exactly 4 keys."""
    result = service._parse_factors({})

    assert all(v == 0.0 for v in result.values())
    assert len(result) == 4


# ═══════════════════════════════════════════════════════════════════════════════
# 5. _compute_score() — weighted aggregation
# ═══════════════════════════════════════════════════════════════════════════════

def test_compute_score_all_ones_returns_one(service):
    """All factors at 1.0 → composite score is 1.0 (weights sum to 1)."""
    factors = {k: 1.0 for k in FACTOR_WEIGHTS}

    assert service._compute_score(factors) == 1.0


def test_compute_score_all_minus_ones_returns_minus_one(service):
    """All factors at -1.0 → composite score is -1.0."""
    factors = {k: -1.0 for k in FACTOR_WEIGHTS}

    assert service._compute_score(factors) == -1.0


def test_compute_score_all_zeros_returns_zero(service):
    """All factors at 0.0 → score = 0.0."""
    factors = {k: 0.0 for k in FACTOR_WEIGHTS}

    assert service._compute_score(factors) == 0.0


def test_compute_score_partial_factors_correct(service):
    """Known factor values → score matches weighted formula."""
    factors = {"market_impact": 0.5, "tone": 0.5, "source_quality": 0.5, "context": 0.5}
    expected = round(0.5 * 0.30 + 0.5 * 0.40 + 0.5 * 0.10 + 0.5 * 0.20, 4)

    assert service._compute_score(factors) == expected


def test_compute_score_mixed_factors(service):
    """Mixed positive/negative factors → weighted average computed correctly."""
    factors = {"market_impact": 1.0, "tone": -1.0, "source_quality": 0.0, "context": 0.0}
    # 1.0*0.30 + (-1.0)*0.40 + 0.0*0.10 + 0.0*0.20 = -0.10
    expected = round(1.0 * 0.30 + (-1.0) * 0.40, 4)

    assert service._compute_score(factors) == expected


def test_compute_score_asymmetric_factors(service):
    """Manually verified asymmetric factor values."""
    factors = {"market_impact": 0.8, "tone": 0.6, "source_quality": 0.4, "context": 0.5}
    expected = round((0.8 * 0.30) + (0.6 * 0.40) + (0.4 * 0.10) + (0.5 * 0.20), 4)

    assert service._compute_score(factors) == expected


def test_compute_score_missing_factor_key_defaults_to_zero(service):
    """Missing factor key in dict treated as 0.0 via .get() fallback."""
    factors = {"market_impact": 0.5, "tone": 0.5}
    expected = round((0.5 * 0.3) + (0.5 * 0.4) + (0.0 * 0.1) + (0.0 * 0.2), 4)

    assert service._compute_score(factors) == expected


def test_compute_score_clamped_to_max_1(service):
    """Score clamp: even at max factors, result never exceeds 1.0."""
    factors = {k: 1.0 for k in FACTOR_WEIGHTS}

    assert service._compute_score(factors) <= 1.0


def test_compute_score_clamped_to_min_neg1(service):
    """Score clamp: even at min factors, result never goes below -1.0."""
    factors = {k: -1.0 for k in FACTOR_WEIGHTS}

    assert service._compute_score(factors) >= -1.0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Score → label boundary tests
# ═══════════════════════════════════════════════════════════════════════════════

def test_score_above_0_1_is_positive(service):
    """score > 0.1 → label is positive."""
    response = llm_response({
        "AAPL": {
            "factor_breakdown": {"market_impact": 0.5, "tone": 0.5, "source_quality": 0.5, "context": 0.5},
            "reasoning": "Bullish.",
        }
    })

    result = service._parse_response(response, {"AAPL": {"OfficialName": "Apple Inc."}})

    assert result["AAPL"]["sentiment_label"] == "positive"


def test_score_below_minus_0_1_is_negative(service):
    """score < -0.1 → label is negative."""
    response = llm_response({
        "MSFT": {
            "factor_breakdown": {"market_impact": -0.5, "tone": -0.5, "source_quality": -0.5, "context": -0.5},
            "reasoning": "Bearish.",
        }
    })

    result = service._parse_response(response, {"MSFT": {"OfficialName": "Microsoft Corporation"}})

    assert result["MSFT"]["sentiment_label"] == "negative"


def test_score_between_boundaries_is_neutral(service):
    """score within [-0.1, 0.1] → label is neutral."""
    response = llm_response({
        "TSLA": {
            "sentiment_score": 0.05,
            "factor_breakdown": {k: 0.0 for k in FACTOR_WEIGHTS},
            "reasoning": "Flat news.",
        }
    })

    result = service._parse_response(response, {"TSLA": {"OfficialName": "Tesla Inc."}})

    assert result["TSLA"]["sentiment_label"] == "neutral"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. _extract_json() — JSON extraction from raw LLM output
# ═══════════════════════════════════════════════════════════════════════════════

def test_extract_json_plain_object(service):
    """Plain JSON string → correctly extracted."""
    text = '{"ticker_sentiments": {"AAPL": {"sentiment_score": 0.8}}}'

    result = service._extract_json(text)

    assert result["ticker_sentiments"]["AAPL"]["sentiment_score"] == 0.8


def test_extract_json_markdown_fenced(service):
    """JSON inside a markdown code fence → correctly extracted."""
    text = '```json\n{"ticker_sentiments": {"MSFT": {"sentiment_score": -0.5}}}\n```'

    result = service._extract_json(text)

    assert result["ticker_sentiments"]["MSFT"]["sentiment_score"] == -0.5


def test_extract_json_backtick_fence_no_language_label(service):
    """Backtick fences without 'json' label → still extracted."""
    text = '```\n{"key": "val"}\n```'

    result = service._extract_json(text)

    assert result == {"key": "val"}


def test_extract_json_with_llm_preamble(service):
    """JSON preceded by LLM preamble text → correctly extracted."""
    text = 'Here is my analysis:\n{"ticker_sentiments": {"GOOGL": {"sentiment_score": 0.3}}}'

    result = service._extract_json(text)

    assert result["ticker_sentiments"]["GOOGL"]["sentiment_score"] == 0.3


def test_extract_json_ignores_trailing_text_after_json(service):
    """JSON embedded between preamble and trailing text → JSON extracted correctly."""
    text = (
        'Analysis complete. '
        '{"ticker_sentiments": {"AAPL": {"score": 0.9}}} '
        'Here is my full reasoning for the above.'
    )

    result = service._extract_json(text)

    assert result is not None
    assert result["ticker_sentiments"]["AAPL"]["score"] == 0.9


def test_extract_json_nested_objects(service):
    """Deeply nested JSON structures are parsed correctly."""
    obj = {"a": {"b": {"c": {"d": 1}}}}
    text = json.dumps(obj)

    assert service._extract_json(text) == obj


def test_extract_json_empty_string_returns_none(service):
    """Empty string → None."""
    assert service._extract_json("") is None


def test_extract_json_none_input_returns_none(service):
    """None input → None."""
    assert service._extract_json(None) is None


def test_extract_json_whitespace_only_returns_none(service):
    """Whitespace-only string → None."""
    assert service._extract_json("   \n\t  ") is None


def test_extract_json_no_braces_returns_none(service):
    """Plain text without any JSON → None."""
    assert service._extract_json("This is just plain text with no JSON.") is None


def test_extract_json_only_opening_brace_returns_none(service):
    """Only opening brace, no closing → None."""
    assert service._extract_json("{") is None


# ═══════════════════════════════════════════════════════════════════════════════
# 8. _repair_truncated_json() — JSON repair from token limit cuts
# ═══════════════════════════════════════════════════════════════════════════════

def test_repair_truncated_json_closes_open_braces(service):
    """Truncated JSON with unclosed braces → repaired string has matching braces."""
    truncated = '{"ticker_sentiments": {"AAPL": {"sentiment_score": 0.8'

    repaired = service._repair_truncated_json(truncated)

    assert repaired is not None
    assert repaired.count("{") == repaired.count("}")


def test_repair_one_missing_brace_produces_valid_json(service):
    """One unmatched opening brace → repaired and parseable."""
    truncated = '{"a": {"b": 1}'

    repaired = service._repair_truncated_json(truncated)

    assert repaired is not None
    parsed = json.loads(repaired)
    assert parsed["a"]["b"] == 1


def test_repair_trailing_comma_removed(service):
    """Trailing comma before repair is stripped so JSON is valid."""
    truncated = '{"a": 1, "b": 2,'

    repaired = service._repair_truncated_json(truncated)

    assert repaired is not None
    parsed = json.loads(repaired)
    assert parsed["a"] == 1


def test_repair_missing_bracket_closed(service):
    """Missing closing bracket and brace are appended → parseable JSON."""
    truncated = '{"items": [1, 2, 3'

    repaired = service._repair_truncated_json(truncated)

    assert repaired is not None
    parsed = json.loads(repaired)
    assert parsed["items"] == [1, 2, 3]


def test_repair_dangling_colon_gets_null(service):
    """Truncated mid-value (dangling colon) gets 'null' appended."""
    truncated = '{"key":'

    repaired = service._repair_truncated_json(truncated)

    assert repaired is not None
    parsed = json.loads(repaired)
    assert parsed["key"] is None


def test_repair_truncated_string_value_closed(service):
    """Truncated mid-string gets quotes closed."""
    truncated = '{"key": "partial val'

    repaired = service._repair_truncated_json(truncated)

    assert repaired is not None
    parsed = json.loads(repaired)
    assert "key" in parsed


def test_repair_balanced_json_returned_unchanged(service):
    """Already-balanced JSON → returned as-is."""
    balanced = '{"key": "value"}'

    result = service._repair_truncated_json(balanced)

    assert result == balanced


def test_repair_more_closes_than_opens_returns_none(service):
    """More closing braces than opening → structurally broken → None."""
    broken = '{"key": "value"}}}'

    result = service._repair_truncated_json(broken)

    assert result is None


def test_repair_more_closing_brackets_returns_none(service):
    """More closing brackets than opening → structurally broken → None."""
    broken = '{"a": [1]]}'

    assert service._repair_truncated_json(broken) is None


# ═══════════════════════════════════════════════════════════════════════════════
# 9. _format_tickers_for_prompt()
# ═══════════════════════════════════════════════════════════════════════════════

def test_format_tickers_single(service):
    """Single ticker formatted correctly with name and event type."""
    meta = {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}}

    result = service._format_tickers_for_prompt(meta)

    assert "AAPL" in result
    assert "Apple Inc." in result
    assert "EARNINGS" in result


def test_format_tickers_multi_one_line_each(service):
    """Multiple tickers each get their own line."""
    meta = {
        "AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"},
        "MSFT": {"OfficialName": "Microsoft Corporation", "event_type": "NEWS"},
        "GOOGL": {"OfficialName": "Alphabet Inc.", "event_type": "PRODUCT_LAUNCH"},
    }

    result = service._format_tickers_for_prompt(meta)
    lines = [l for l in result.strip().split("\n") if l.strip()]

    assert len(lines) == 3


def test_format_tickers_missing_official_name_uses_ticker(service):
    """Missing OfficialName defaults to ticker symbol."""
    meta = {"XYZ": {"event_type": "EARNINGS"}}

    result = service._format_tickers_for_prompt(meta)

    assert "XYZ (XYZ)" in result


def test_format_tickers_missing_event_type_shows_unknown(service):
    """Missing event_type defaults to 'Unknown'."""
    meta = {"XYZ": {"OfficialName": "XYZ Corp"}}

    result = service._format_tickers_for_prompt(meta)

    assert "Unknown" in result


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Fallback generation
# ═══════════════════════════════════════════════════════════════════════════════

def test_fallback_ticker_has_correct_structure(service):
    """Fallback ticker has neutral score, label, reasoning, and zero factors."""
    fb = service._create_fallback_ticker("AAPL", "Apple Inc.")

    assert fb["sentiment_score"] == 0.0
    assert fb["sentiment_label"] == "neutral"
    assert fb["reasoning"] == FALLBACK_REASONING
    assert fb["official_name"] == "Apple Inc."
    assert all(v == 0.0 for v in fb["factor_breakdown"].values())


def test_fallback_sentiments_covers_all_tickers(service):
    """Fallback sentiments creates entries for every ticker in metadata."""
    meta = {
        "AAPL": {"OfficialName": "Apple Inc."},
        "MSFT": {"OfficialName": "Microsoft Corporation"},
        "GOOGL": {"OfficialName": "Alphabet Inc."},
    }

    result = service._create_fallback_sentiments(meta)

    assert set(result.keys()) == {"AAPL", "MSFT", "GOOGL"}
    for data in result.values():
        assert data["sentiment_score"] == 0.0


def test_fallback_uses_ticker_as_name_if_no_official_name(service):
    """If OfficialName missing, ticker symbol is used as name."""
    meta = {"XYZ": {"event_type": "UNKNOWN"}}

    result = service._create_fallback_sentiments(meta)

    assert result["XYZ"]["official_name"] == "XYZ"


def test_fallback_factors_are_independent_copies(service):
    """Each fallback ticker gets its own copy of factors (no shared mutation)."""
    fb1 = service._create_fallback_ticker("A", "A")
    fb2 = service._create_fallback_ticker("B", "B")
    fb1["factor_breakdown"]["market_impact"] = 999

    assert fb2["factor_breakdown"]["market_impact"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Text truncation
# ═══════════════════════════════════════════════════════════════════════════════

async def test_long_text_truncated_to_max_chars(service):
    """Text longer than MAX_TEXT_CHARS is truncated before the LLM call."""
    long_text = "x" * (MAX_TEXT_CHARS + 1000)

    service._analyze_single = AsyncMock(
        return_value=LLMSentimentResult(ticker_sentiments={}, analysis_successful=True)
    )

    await service._analyze_tickers(long_text, {"AAPL": {"OfficialName": "Apple Inc."}})

    passed_text = service._analyze_single.call_args[0][0]
    assert len(passed_text) <= MAX_TEXT_CHARS + 3  # +3 for "..."
    assert passed_text.endswith("...")


async def test_short_text_not_truncated(service):
    """Text shorter than MAX_TEXT_CHARS passes through unchanged."""
    short_text = "AAPL is great"

    service._analyze_single = AsyncMock(
        return_value=LLMSentimentResult(ticker_sentiments={}, analysis_successful=True)
    )

    await service._analyze_tickers(short_text, {"AAPL": {"OfficialName": "Apple Inc."}})

    passed_text = service._analyze_single.call_args[0][0]
    assert passed_text == short_text


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Batching
# ═══════════════════════════════════════════════════════════════════════════════

async def test_batching_triggered_above_threshold(service):
    """More than MAX_TICKERS_PER_CALL tickers → _analyze_batched called, not _analyze_single."""
    ticker_metadata = {
        f"TICK{i}": {"OfficialName": f"Company {i}", "event_type": "NEWS"}
        for i in range(MAX_TICKERS_PER_CALL + 1)
    }

    service._analyze_batched = AsyncMock(
        return_value=LLMSentimentResult(ticker_sentiments={}, analysis_successful=True)
    )
    service._analyze_single = AsyncMock(
        return_value=LLMSentimentResult(ticker_sentiments={}, analysis_successful=True)
    )

    await service._analyze_tickers("Market news about many stocks.", ticker_metadata)

    service._analyze_batched.assert_called_once()
    service._analyze_single.assert_not_called()


async def test_single_analysis_used_below_threshold(service):
    """Tickers at or below MAX_TICKERS_PER_CALL → _analyze_single called directly."""
    ticker_metadata = {
        f"TICK{i}": {"OfficialName": f"Company {i}", "event_type": "NEWS"}
        for i in range(MAX_TICKERS_PER_CALL)
    }

    service._analyze_single = AsyncMock(
        return_value=LLMSentimentResult(ticker_sentiments={}, analysis_successful=True)
    )
    service._analyze_batched = AsyncMock(
        return_value=LLMSentimentResult(ticker_sentiments={}, analysis_successful=True)
    )

    await service._analyze_tickers("Market news.", ticker_metadata)

    service._analyze_single.assert_called_once()
    service._analyze_batched.assert_not_called()


async def test_batched_results_merged_across_batches(service):
    """7 tickers across 2 batches → all 7 appear in final merged result."""
    ticker_metadata = {
        f"T{i}": {"OfficialName": f"Company {i}", "event_type": "EARNINGS"}
        for i in range(7)
    }

    async def fake_single(text, meta):
        return LLMSentimentResult(
            {t: {"sentiment_score": 0.5, "sentiment_label": "positive",
                 "reasoning": "ok", "factor_breakdown": {}}
             for t in meta}, True
        )

    service._analyze_single = AsyncMock(side_effect=fake_single)

    result = await service._analyze_tickers("text", ticker_metadata)

    assert len(result.ticker_sentiments) == 7


async def test_one_batch_fails_marks_overall_unsuccessful(service):
    """If one batch fails, overall result is marked unsuccessful with error."""
    ticker_metadata = {
        f"T{i}": {"OfficialName": f"Company {i}", "event_type": "EARNINGS"}
        for i in range(7)
    }

    call_count = 0

    async def alternating_result(text, meta):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return LLMSentimentResult({}, False, "batch 1 failed")
        return LLMSentimentResult({}, True)

    service._analyze_single = AsyncMock(side_effect=alternating_result)

    result = await service._analyze_tickers("text", ticker_metadata)

    assert result.analysis_successful is False
    assert "batch 1 failed" in result.error_message


# ═══════════════════════════════════════════════════════════════════════════════
# 13. LLM failure / recovery
# ═══════════════════════════════════════════════════════════════════════════════

async def test_llm_chain_failure_returns_neutral_fallback(service):
    """LLM always raises exception and recovery fails → neutral fallback for all tickers."""
    mock_chain = AsyncMock()
    mock_chain.ainvoke = AsyncMock(side_effect=Exception("Groq API unavailable"))
    service.llm.__or__ = MagicMock(return_value=mock_chain)
    service._try_recover_partial = AsyncMock(return_value=None)

    ticker_metadata = {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}}

    result = await service._analyze_single("Apple news.", ticker_metadata)

    assert result.analysis_successful is False
    assert result.ticker_sentiments["AAPL"]["sentiment_label"] == "neutral"
    assert result.ticker_sentiments["AAPL"]["sentiment_score"] == 0.0


async def test_llm_failure_error_message_contains_exception_text(service):
    """Failed analysis error message includes the exception text."""
    mock_chain = AsyncMock()
    mock_chain.ainvoke = AsyncMock(side_effect=Exception("Groq 429 rate limited"))
    service.llm.__or__ = MagicMock(return_value=mock_chain)
    service._try_recover_partial = AsyncMock(return_value=None)

    ticker_metadata = {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}}

    result = await service._analyze_single("text", ticker_metadata)

    assert "Groq 429 rate limited" in result.error_message


async def test_llm_failure_retries_max_times(service):
    """LLM chain is called exactly MAX_RETRIES times before giving up."""
    mock_chain = AsyncMock()
    mock_chain.ainvoke = AsyncMock(side_effect=Exception("API Error"))
    service.llm.__or__ = MagicMock(return_value=mock_chain)
    service._try_recover_partial = AsyncMock(return_value=None)

    ticker_metadata = {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}}

    await service._analyze_single("text", ticker_metadata)

    assert mock_chain.ainvoke.call_count == MAX_RETRIES


async def test_partial_recovery_used_on_final_retry(service):
    """JsonOutputParser fails but raw recovery succeeds → partial result returned."""
    mock_chain = AsyncMock()
    mock_chain.ainvoke = AsyncMock(side_effect=Exception("Parse error"))
    service.llm.__or__ = MagicMock(return_value=mock_chain)

    recovered = LLMSentimentResult(
        ticker_sentiments={
            "AAPL": {
                "sentiment_score": 0.6,
                "sentiment_label": "positive",
                "reasoning": "Recovered from raw output.",
                "factor_breakdown": ALL_POSITIVE_FACTORS,
                "official_name": "Apple Inc.",
            }
        },
        analysis_successful=True,
    )
    service._try_recover_partial = AsyncMock(return_value=recovered)

    ticker_metadata = {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}}

    result = await service._analyze_single("Apple news.", ticker_metadata)

    assert result.analysis_successful is True
    assert result.ticker_sentiments["AAPL"]["sentiment_label"] == "positive"


async def test_first_attempt_succeeds_no_retries(service):
    """First LLM call succeeds → chain called exactly once, no retries."""
    mock_chain = AsyncMock(return_value={
        "ticker_sentiments": {
            "AAPL": {
                "sentiment_score": 0.5,
                "factor_breakdown": {"market_impact": 0.5, "tone": 0.5, "source_quality": 0.0, "context": 0.0},
                "reasoning": "ok",
            }
        }
    })
    service.llm.__or__ = MagicMock(return_value=MagicMock(ainvoke=mock_chain))

    ticker_metadata = {"AAPL": {"OfficialName": "Apple Inc.", "event_type": "EARNINGS"}}

    result = await service._analyze_single("AAPL is great", ticker_metadata)

    assert result.analysis_successful is True
    assert mock_chain.call_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# 14. Singleton pattern
# ═══════════════════════════════════════════════════════════════════════════════

def test_singleton_returns_same_instance():
    """Multiple instantiations return the same object."""
    with patch("app.services._05_sentiment.ChatGroq"):
        svc1 = LLMSentimentService()
        svc2 = LLMSentimentService()
        assert svc1 is svc2


def test_singleton_initialized_flag_prevents_reinit():
    """Second __init__ call doesn't re-initialize when _initialized is True."""
    with patch("app.services._05_sentiment.ChatGroq"):
        svc = LLMSentimentService()
        svc._initialized = True
        svc.model_name = "first-model"
        LLMSentimentService.__init__(svc, model_name="second-model")
        assert svc.model_name == "first-model"


# ═══════════════════════════════════════════════════════════════════════════════
# 15. LLMSentimentResult dataclass
# ═══════════════════════════════════════════════════════════════════════════════

def test_result_dataclass_defaults():
    """Defaults are analysis_successful=True, error_message=None."""
    result = LLMSentimentResult(ticker_sentiments={"AAPL": {}})

    assert result.analysis_successful is True
    assert result.error_message is None


def test_result_dataclass_custom_values():
    """Custom values are stored correctly."""
    result = LLMSentimentResult(
        ticker_sentiments={}, analysis_successful=False, error_message="fail"
    )

    assert result.analysis_successful is False
    assert result.error_message == "fail"


# ═══════════════════════════════════════════════════════════════════════════════
# 16. Constants validation
# ═══════════════════════════════════════════════════════════════════════════════

def test_factor_weights_sum_to_one():
    """Factor weights should sum to 1.0 for valid scoring."""
    assert round(sum(FACTOR_WEIGHTS.values()), 4) == 1.0


def test_factor_weights_has_four_factors():
    """Exactly 4 factors defined with expected names."""
    assert len(FACTOR_WEIGHTS) == 4
    assert set(FACTOR_WEIGHTS.keys()) == {"market_impact", "tone", "source_quality", "context"}


def test_fallback_factors_all_zero():
    """FALLBACK_FACTORS are all 0.0."""
    assert all(v == 0.0 for v in FALLBACK_FACTORS.values())


def test_max_retries_positive():
    """MAX_RETRIES is a positive integer."""
    assert MAX_RETRIES > 0


def test_max_tickers_per_call_positive():
    """MAX_TICKERS_PER_CALL is a positive integer."""
    assert MAX_TICKERS_PER_CALL > 0


def test_max_text_chars_positive():
    """MAX_TEXT_CHARS is a positive integer."""
    assert MAX_TEXT_CHARS > 0