"""
Test: _propose_new_events_with_llm
- Token count comparison: without vs with existing_events_str
- Verify existing_events section is included in prompt when provided
- Verify section is absent when not provided
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services._03_event_identification import EventIdentifierService

# ==========================================================
# FIXTURES
# ==========================================================

EVENT_LIST = {
    "EARNINGS_BEAT": {"event_category": "COMPANY_EVENT", "meaning": "Reported earnings exceed market consensus expectations."},
    "EARNINGS_MISS": {"event_category": "COMPANY_EVENT", "meaning": "Reported earnings fall below market consensus expectations."},
    "INSIDER_BUYING": {"event_category": "COMPANY_EVENT", "meaning": "Company executives or board members purchase company shares, signaling confidence in the company."},
    "INSIDER_SELLING": {"event_category": "COMPANY_EVENT", "meaning": "Company executives or board members sell company shares, potentially signaling reduced confidence or personal liquidity needs."},
    "GUIDANCE_UPGRADE": {"event_category": "COMPANY_EVENT", "meaning": "Company raises forward-looking financial guidance."},
    "GUIDANCE_DOWNGRADE": {"event_category": "COMPANY_EVENT", "meaning": "Company lowers forward-looking financial guidance."},
    "MERGER": {"event_category": "COMPANY_EVENT", "meaning": "Two companies combine to form a single entity."},
    "ACQUISITION": {"event_category": "COMPANY_EVENT", "meaning": "Company acquires controlling interest in another company."},
    "DIVESTITURE": {"event_category": "COMPANY_EVENT", "meaning": "Company sells or spins off a business unit or asset."},
    "IPO": {"event_category": "COMPANY_EVENT", "meaning": "Company offers shares to the public for the first time."},
    "SECONDARY_OFFERING": {"event_category": "COMPANY_EVENT", "meaning": "Company issues additional shares after an initial public offering."},
    "SHARE_BUYBACK": {"event_category": "COMPANY_EVENT", "meaning": "Company repurchases its own shares from the market."},
    "DIVIDEND_INCREASE": {"event_category": "COMPANY_EVENT", "meaning": "Company increases its dividend payout to shareholders."},
    "DIVIDEND_CUT": {"event_category": "COMPANY_EVENT", "meaning": "Company reduces or suspends its dividend payout."},
    "MANAGEMENT_CHANGE": {"event_category": "COMPANY_EVENT", "meaning": "Change in senior management or executive leadership."},
    "REGULATORY_APPROVAL": {"event_category": "EXTERNAL_EVENT", "meaning": "Company receives approval from a regulatory authority."},
    "REGULATORY_PENALTY": {"event_category": "EXTERNAL_EVENT", "meaning": "Company is fined or sanctioned by a regulatory authority."},
    "REGULATORY_INVESTIGATION": {"event_category": "EXTERNAL_EVENT", "meaning": "A regulatory authority initiates or announces an investigation into the company's operations, compliance, or business practices."},
    "PRODUCT_LAUNCH": {"event_category": "COMPANY_EVENT", "meaning": "Company introduces a new product or service to the market."},
    "PRODUCT_RECALL": {"event_category": "COMPANY_EVENT", "meaning": "Company recalls products due to safety or quality issues."},
    "STRATEGIC_PARTNERSHIP": {"event_category": "COMPANY_EVENT", "meaning": "Company enters a formal partnership to pursue strategic objectives."},
    "DEBT_ISSUANCE": {"event_category": "COMPANY_EVENT", "meaning": "Company raises capital by issuing debt instruments."},
    "DEBT_RESTRUCTURING": {"event_category": "COMPANY_EVENT", "meaning": "Company renegotiates or modifies existing debt obligations."},
    "BANKRUPTCY": {"event_category": "COMPANY_EVENT", "meaning": "Company files for legal bankruptcy protection."},
    "RESTRUCTURING": {"event_category": "COMPANY_EVENT", "meaning": "Company reorganizes operations to improve financial or operational performance."},
    "LITIGATION": {"event_category": "EXTERNAL_EVENT", "meaning": "Company is involved in a legal dispute or lawsuit."},
    "SETTLEMENT": {"event_category": "COMPANY_EVENT", "meaning": "Company resolves a legal dispute through an agreed settlement."},
    "PATENT_DISPUTE": {"event_category": "EXTERNAL_EVENT", "meaning": "Company is involved in a legal dispute over intellectual property rights."},
    "STOCK_SPLIT": {"event_category": "COMPANY_EVENT", "meaning": "Company increases share count by splitting existing shares."},
    "SUPPLY_CHAIN_DISRUPTION": {"event_category": "EXTERNAL_EVENT", "meaning": "Significant external disruptions to sourcing, logistics, or manufacturing inputs affecting the company."},
    "GOVERNMENT_INVESTMENT": {"event_category": "EXTERNAL_EVENT", "meaning": "Government takes equity stakes, provides bailouts, or makes strategic investments in a company."},
    "COMPANY_INVESTMENT": {"event_category": "COMPANY_EVENT", "meaning": "Company allocates significant capital to strategic projects, initiatives, or infrastructure."},
    "DATA_BREACH": {"event_category": "COMPANY_EVENT", "meaning": "Unauthorized access to or exposure of company or customer data."},
    "NATURAL_DISASTER_IMPACT": {"event_category": "EXTERNAL_EVENT", "meaning": "Company operations are materially affected by a natural disaster."},
    "TECHNOLOGY_UPGRADE": {"event_category": "COMPANY_EVENT", "meaning": "Company implements significant improvements to technology systems or platforms."},
    "TECHNOLOGY_FAILURE": {"event_category": "COMPANY_EVENT", "meaning": "Company experiences a material technology or system outage."},
    "MARKET_ENTRY": {"event_category": "COMPANY_EVENT", "meaning": "Company enters a new geographic or product market."},
    "COMPETITOR_ANNOUNCEMENT": {"event_category": "EXTERNAL_EVENT", "meaning": "Action or announcement by a competitor that may materially affect investor perception of the company."},
    "EXTERNAL_INDUSTRY_GROWTH": {"event_category": "EXTERNAL_EVENT", "meaning": "Investors may adjust valuations and expectations for companies due to projected growth in the broader industry or sector."},
    "INVESTOR_ACTION": {"event_category": "INVESTOR_EVENT", "meaning": "Observable investor activity related to the stock."},
    "INVESTOR_OPINION": {"event_category": "INVESTOR_EVENT", "meaning": "Investor sentiment, predictions, or subjective opinions about the stock."},
    "EARNINGS_CALL": {"event_category": "COMPANY_EVENT", "meaning": "Statements, metrics, or forward-looking commentary made by company executives during an official earnings call."},
    "EQUITY_AND_DEBT_FINANCING_PLAN": {"event_category": "COMPANY_EVENT", "meaning": "The company announces a plan to raise significant capital through equity or debt instruments."},
    "PRODUCT_LINE_DISCONTINUATION": {"event_category": "COMPANY_EVENT", "meaning": "Company permanently stops producing or selling a specific product line."},
}

UNMATCHED_COMPANY = {
    "TSMC": {"primary_event_category": "COMPANY_EVENT"},
}

UNMATCHED_EXTERNAL = {
    "AAPL": {"primary_event_category": "EXTERNAL_EVENT"},
}

TEXT = "TSMC has announced a joint venture with Samsung to co-develop next-generation 2nm chips in Arizona."

MOCK_PROPOSAL = {
    "TSMC": {
        "primary_event_category": "COMPANY_EVENT",
        "proposed_event_name": "JOINT_VENTURE",
        "proposed_description": "TSMC and Samsung announced a joint venture for 2nm chip development.",
        "meaning": "Two companies co-invest in a manufacturing or R&D facility to share costs and capabilities.",
        "confidence": 0.88,
    }
}


def build_service():
    service = EventIdentifierService(event_list=EVENT_LIST)
    # replace LLM with mock so no real API calls
    service.llm = MagicMock()
    service.parser = MagicMock()
    return service


def build_filtered_events_str(event_list: dict, categories: set) -> str:
    return "\n".join(
        f"- {name}"
        for name, meta in event_list.items()
        if meta.get("event_category") in categories
    )


# ==========================================================
# TOKEN COUNT COMPARISON
# ==========================================================

def test_token_count_comparison():
    """
    Prints token estimate with and without existing_events_str.
    Not a pass/fail test — informational.
    """
    categories = {d["primary_event_category"] for d in UNMATCHED_COMPANY.values()}
    filtered = build_filtered_events_str(EVENT_LIST, categories)
    existing_section = (
        f"Existing events in this category (DO NOT propose events already covered by these):\n{filtered}\n\n"
    )

    base_prompt = (
        f"Full Post:\n{TEXT}\n\n"
        f"Unmatched Tickers:\n{json.dumps(UNMATCHED_COMPANY, indent=2)}\n\n"
    )

    tokens_without = len(base_prompt) // 4
    tokens_with = len(base_prompt + existing_section) // 4
    diff = tokens_with - tokens_without

    print(f"\n--- Token Count Comparison (COMPANY_EVENT) ---")
    print(f"Without existing_events_str : ~{tokens_without} tokens")
    print(f"With existing_events_str    : ~{tokens_with} tokens")
    print(f"Difference                  : ~{diff} tokens")
    print(f"\nExisting events section injected:\n{existing_section}")

    assert tokens_with > tokens_without


# ==========================================================
# PROMPT CONTENT TESTS
# ==========================================================

@pytest.mark.asyncio
async def test_existing_events_section_included_in_prompt():
    """
    When existing_events_str is provided, the prompt must contain the guardrail section.
    """
    service = build_service()
    categories = {d["primary_event_category"] for d in UNMATCHED_COMPANY.values()}
    filtered = build_filtered_events_str(EVENT_LIST, categories)

    captured_prompts = []

    original_init = service.llm.__class__

    # intercept chain.ainvoke by patching the parser to capture input
    async def mock_ainvoke(inputs):
        return MOCK_PROPOSAL

    with patch.object(service, "_propose_new_events_with_llm", wraps=service._propose_new_events_with_llm):
        # patch chain construction to capture the rendered prompt
        from langchain_core.prompts import PromptTemplate

        original_format = PromptTemplate.format

        def capturing_format(self_pt, **kwargs):
            rendered = original_format(self_pt, **kwargs)
            captured_prompts.append(rendered)
            return rendered

        with patch.object(PromptTemplate, "format", capturing_format):
            with patch.object(service.llm.__class__, "__or__", return_value=MagicMock(
                ainvoke=AsyncMock(return_value=MOCK_PROPOSAL)
            )):
                # mock the full chain
                mock_chain = MagicMock()
                mock_chain.ainvoke = AsyncMock(return_value=MOCK_PROPOSAL)

                with patch("langchain_core.prompts.PromptTemplate.__or__", return_value=mock_chain):
                    await service._propose_new_events_with_llm(TEXT, UNMATCHED_COMPANY, filtered)

    if captured_prompts:
        assert "DO NOT propose events already covered" in captured_prompts[0]
        assert "EARNINGS_BEAT" in captured_prompts[0]


@pytest.mark.asyncio
async def test_existing_events_section_absent_when_empty():
    """
    When existing_events_str is empty, the guardrail section must not appear.
    """
    service = build_service()
    captured_prompts = []

    from langchain_core.prompts import PromptTemplate
    original_format = PromptTemplate.format

    def capturing_format(self_pt, **kwargs):
        rendered = original_format(self_pt, **kwargs)
        captured_prompts.append(rendered)
        return rendered

    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value=MOCK_PROPOSAL)

    with patch.object(PromptTemplate, "format", capturing_format):
        with patch("langchain_core.prompts.PromptTemplate.__or__", return_value=mock_chain):
            await service._propose_new_events_with_llm(TEXT, UNMATCHED_COMPANY, existing_events_str="")

    if captured_prompts:
        assert "DO NOT propose events already covered" not in captured_prompts[0]


# ==========================================================
# BEHAVIOUR TESTS
# ==========================================================

@pytest.mark.asyncio
async def test_proposal_returns_dict_on_success():
    service = build_service()
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value=MOCK_PROPOSAL)
    mock_chain.__or__ = MagicMock(return_value=mock_chain)

    with patch("langchain_core.prompts.PromptTemplate.__or__", return_value=mock_chain):
        result = await service._propose_new_events_with_llm(TEXT, UNMATCHED_COMPANY)

    assert isinstance(result, dict)
    assert "TSMC" in result


@pytest.mark.asyncio
async def test_proposal_returns_empty_for_no_unmatched():
    service = build_service()
    result = await service._propose_new_events_with_llm(TEXT, {})
    assert result == {}


@pytest.mark.asyncio
async def test_proposal_enforces_category_consistency():
    """
    If LLM returns wrong category, it should be corrected to match input.
    """
    service = build_service()
    wrong_category_response = {
        "TSMC": {
            "primary_event_category": "EXTERNAL_EVENT",  # wrong — should be COMPANY_EVENT
            "proposed_event_name": "JOINT_VENTURE",
            "proposed_description": "Joint venture announcement.",
            "meaning": "Two companies co-invest.",
            "confidence": 0.85,
        }
    }

    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value=wrong_category_response)
    mock_chain.__or__ = MagicMock(return_value=mock_chain)

    with patch("langchain_core.prompts.PromptTemplate.__or__", return_value=mock_chain):
        result = await service._propose_new_events_with_llm(TEXT, UNMATCHED_COMPANY)

    assert result["TSMC"]["primary_event_category"] == "COMPANY_EVENT"


@pytest.mark.asyncio
async def test_proposal_retries_on_failure():
    """
    LLM fails twice then succeeds — should return result on 3rd attempt.
    """
    service = build_service()
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(side_effect=[
        Exception("timeout"),
        Exception("timeout"),
        MOCK_PROPOSAL,
    ])
    mock_chain.__or__ = MagicMock(return_value=mock_chain)

    with patch("langchain_core.prompts.PromptTemplate.__or__", return_value=mock_chain):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service._propose_new_events_with_llm(TEXT, UNMATCHED_COMPANY)

    assert result == MOCK_PROPOSAL


@pytest.mark.asyncio
async def test_proposal_returns_empty_after_all_retries_fail():
    service = build_service()
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(side_effect=Exception("always fails"))

    with patch("langchain_core.prompts.PromptTemplate.__or__", return_value=mock_chain):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service._propose_new_events_with_llm(TEXT, UNMATCHED_COMPANY)

    assert result == {}


# ==========================================================
# FILTERED EVENTS STR TESTS
# ==========================================================

@pytest.mark.asyncio
async def test_filtered_events_str_only_contains_matching_category():
    """
    When unmatched tickers are COMPANY_EVENT, filtered_events_str passed to
    _propose_new_events_with_llm must only contain COMPANY_EVENT events.
    """
    service = build_service()

    captured = {}

    async def capturing_propose(_text, unmatched_tickers, existing_events_str=""):
        captured["unmatched_categories"] = {
            d["primary_event_category"] for d in unmatched_tickers.values()
        }
        captured["existing_events_str"] = existing_events_str
        return {}

    service._propose_new_events_with_llm = capturing_propose

    # Simulate _analyse_events_with_llm returning null event_type (unmatched)
    async def mock_analyse(ticker_inputs, _event_category_map):
        return {
            "tickers": {
                ticker: {
                    "primary_event_category": data.get("primary_event_category"),
                    "event_type": None,
                    "event_description": None,
                }
                for ticker, data in ticker_inputs.items()
            }
        }

    service._analyse_events_with_llm = mock_analyse

    # Simulate _identify_primary_tickers LLM returning COMPANY_EVENT tickers
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value={
        "primary_tickers": ["TSMC"],
        "tickers": {
            "TSMC": {
                "primary_event_category": "COMPANY_EVENT",
                "event_description": "TSMC announced a joint venture with Samsung.",
            }
        }
    })
    mock_chain.__or__ = MagicMock(return_value=mock_chain)

    with patch("langchain_core.prompts.PromptTemplate.__or__", return_value=mock_chain):
        await service._identify_primary_tickers(
            text="TSMC announced a joint venture with Samsung.",
            ticker_metadata={"TSMC": {"sentiment_score": 0.7, "sentiment_label": "positive"}},
        )

    print(f"\n[Filtered Events] unmatched_categories : {captured.get('unmatched_categories')}")
    print(f"[Filtered Events] filtered_events_str  :\n{captured.get('existing_events_str')}")

    assert "unmatched_categories" in captured
    assert "COMPANY_EVENT" in captured["unmatched_categories"]
    assert "EXTERNAL_EVENT" not in captured["unmatched_categories"]

    # every line in filtered_events_str must be a COMPANY_EVENT
    events_str = captured.get("existing_events_str", "")
    assert events_str, "filtered_events_str should not be empty"

    for line in events_str.strip().splitlines():
        event_name = line.lstrip("- ").strip()
        meta = EVENT_LIST.get(event_name)
        assert meta is not None, f"Unknown event in filtered_events_str: {event_name}"
        assert meta["event_category"] == "COMPANY_EVENT", (
            f"{event_name} has category {meta['event_category']}, expected COMPANY_EVENT"
        )


@pytest.mark.asyncio
async def test_filtered_events_str_contains_external_events_only():
    """
    When unmatched tickers are EXTERNAL_EVENT, filtered_events_str must only
    contain EXTERNAL_EVENT events — no COMPANY_EVENT entries.
    """
    service = build_service()
    captured = {}

    async def capturing_propose(text, unmatched_tickers, existing_events_str=""):
        captured["unmatched_categories"] = {
            d["primary_event_category"] for d in unmatched_tickers.values()
        }
        captured["existing_events_str"] = existing_events_str
        return {}

    service._propose_new_events_with_llm = capturing_propose

    async def mock_analyse(ticker_inputs, event_category_map):
        return {
            "tickers": {
                ticker: {
                    "primary_event_category": data.get("primary_event_category"),
                    "event_type": None,
                    "event_description": None,
                }
                for ticker, data in ticker_inputs.items()
            }
        }

    service._analyse_events_with_llm = mock_analyse

    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value={
        "primary_tickers": ["AAPL"],
        "tickers": {
            "AAPL": {
                "primary_event_category": "EXTERNAL_EVENT",
                "event_description": "FTC launched antitrust investigation into Apple.",
            }
        }
    })
    mock_chain.__or__ = MagicMock(return_value=mock_chain)

    with patch("langchain_core.prompts.PromptTemplate.__or__", return_value=mock_chain):
        await service._identify_primary_tickers(
            text="FTC launched antitrust investigation into Apple.",
            ticker_metadata={"AAPL": {"sentiment_score": 0.3, "sentiment_label": "negative"}},
        )

    print(f"\n[Filtered Events] unmatched_categories : {captured.get('unmatched_categories')}")
    print(f"[Filtered Events] filtered_events_str  :\n{captured.get('existing_events_str')}")

    assert "EXTERNAL_EVENT" in captured["unmatched_categories"]
    assert "COMPANY_EVENT" not in captured["unmatched_categories"]

    events_str = captured.get("existing_events_str", "")
    assert events_str, "filtered_events_str should not be empty"

    for line in events_str.strip().splitlines():
        event_name = line.lstrip("- ").strip()
        meta = EVENT_LIST.get(event_name)
        assert meta is not None, f"Unknown event in filtered_events_str: {event_name}"
        assert meta["event_category"] == "EXTERNAL_EVENT", (
            f"{event_name} has category {meta['event_category']}, expected EXTERNAL_EVENT"
        )


@pytest.mark.asyncio
async def test_filtered_events_str_contains_both_categories():
    """
    When unmatched tickers span COMPANY_EVENT and EXTERNAL_EVENT,
    filtered_events_str must contain events from both categories.
    """
    service = build_service()
    captured = {}

    async def capturing_propose(text, unmatched_tickers, existing_events_str=""):
        captured["unmatched_categories"] = {
            d["primary_event_category"] for d in unmatched_tickers.values()
        }
        captured["existing_events_str"] = existing_events_str
        return {}

    service._propose_new_events_with_llm = capturing_propose

    async def mock_analyse(ticker_inputs, event_category_map):
        return {
            "tickers": {
                ticker: {
                    "primary_event_category": data.get("primary_event_category"),
                    "event_type": None,
                    "event_description": None,
                }
                for ticker, data in ticker_inputs.items()
            }
        }

    service._analyse_events_with_llm = mock_analyse

    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value={
        "primary_tickers": ["TSMC", "AAPL"],
        "tickers": {
            "TSMC": {
                "primary_event_category": "COMPANY_EVENT",
                "event_description": "TSMC announced a joint venture.",
            },
            "AAPL": {
                "primary_event_category": "EXTERNAL_EVENT",
                "event_description": "FTC launched antitrust investigation into Apple.",
            },
        }
    })
    mock_chain.__or__ = MagicMock(return_value=mock_chain)

    with patch("langchain_core.prompts.PromptTemplate.__or__", return_value=mock_chain):
        await service._identify_primary_tickers(
            text="TSMC announced a joint venture. FTC launched antitrust investigation into Apple.",
            ticker_metadata={
                "TSMC": {"sentiment_score": 0.7, "sentiment_label": "positive"},
                "AAPL": {"sentiment_score": 0.3, "sentiment_label": "negative"},
            },
        )

    print(f"\n[Mixed Categories] unmatched_categories : {captured.get('unmatched_categories')}")
    print(f"[Mixed Categories] filtered_events_str  :\n{captured.get('existing_events_str')}")

    assert "COMPANY_EVENT" in captured["unmatched_categories"]
    assert "EXTERNAL_EVENT" in captured["unmatched_categories"]

    events_str = captured.get("existing_events_str", "")
    assert events_str, "filtered_events_str should not be empty"

    found_categories = set()
    for line in events_str.strip().splitlines():
        event_name = line.lstrip("- ").strip()
        meta = EVENT_LIST.get(event_name)
        assert meta is not None, f"Unknown event in filtered_events_str: {event_name}"
        found_categories.add(meta["event_category"])

    assert "COMPANY_EVENT" in found_categories, "filtered_events_str missing COMPANY_EVENT entries"
    assert "EXTERNAL_EVENT" in found_categories, "filtered_events_str missing EXTERNAL_EVENT entries"
