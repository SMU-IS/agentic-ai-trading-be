"""
Unit Tests — EventIdentifierService
File: app/tests/test_event_identification.py

Run from event-identification-service/:
    pytest
"""

import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture
def dummy_event_list():
    return {
        "EARNINGS_BEAT": {"event_category": "COMPANY_EVENT", "meaning": "Company beat earnings"},
        "RATE_HIKE": {"event_category": "EXTERNAL_EVENT", "meaning": "Central bank raised rates"},
    }


@pytest.fixture
def service(dummy_event_list):
    """
    Import the real EventIdentifierService with all LLM deps patched.
    Pop the conftest whole-module mock first so we get the real class.
    """
    sys.modules.pop("app.services._03_event_identification", None)

    with patch("app.services._03_event_identification.ChatGroq"), \
         patch("app.services._03_event_identification.JsonOutputParser"), \
         patch("app.services._03_event_identification.PromptTemplate"):
        from app.services._03_event_identification import EventIdentifierService
        svc = EventIdentifierService(event_list=dummy_event_list)
        svc.llm = MagicMock()
        svc.parser = MagicMock()
        yield svc


# ─── __init__ LLM failure ─────────────────────────────────────────────────────

def test_init_llm_failure_sets_none(dummy_event_list):
    sys.modules.pop("app.services._03_event_identification", None)

    with patch("app.services._03_event_identification.ChatGroq", side_effect=Exception("no key")), \
         patch("app.services._03_event_identification.JsonOutputParser"), \
         patch("app.services._03_event_identification.PromptTemplate"):
        from app.services._03_event_identification import EventIdentifierService
        svc = EventIdentifierService(event_list=dummy_event_list)

    assert svc.llm is None
    assert svc.parser is None


# ─── _propose_new_events_with_llm() ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_propose_no_llm_returns_empty(service):
    service.llm = None
    result = await service._propose_new_events_with_llm(
        text="some text",
        unmatched_tickers={"AAPL": {"primary_event_category": "COMPANY_EVENT"}},
    )
    assert result == {}


@pytest.mark.asyncio
async def test_propose_empty_unmatched_returns_empty(service):
    result = await service._propose_new_events_with_llm(
        text="some text",
        unmatched_tickers={},
    )
    assert result == {}


@pytest.mark.asyncio
async def test_propose_success(service):
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value={
        "AAPL": {
            "primary_event_category": "COMPANY_EVENT",
            "proposed_event_name": "CEO_DEPARTURE",
            "proposed_description": "CEO resigned",
            "meaning": "Leadership change",
            "confidence": 0.9,
        }
    })

    with patch("app.services._03_event_identification.PromptTemplate") as mock_pt:
        mock_pt.return_value.__or__ = MagicMock(return_value=MagicMock())
        # patch the chain building inline
        service.llm.__or__ = MagicMock()
        service.parser.__ror__ = MagicMock()

        # directly mock the chain creation by patching ainvoke on chain
        with patch.object(service, "_propose_new_events_with_llm", wraps=service._propose_new_events_with_llm):
            # build a fake chain via __or__
            fake_chain = MagicMock()
            fake_chain.ainvoke = AsyncMock(return_value={
                "AAPL": {
                    "primary_event_category": "COMPANY_EVENT",
                    "proposed_event_name": "CEO_DEPARTURE",
                    "proposed_description": "CEO resigned",
                    "meaning": "Leadership change",
                    "confidence": 0.9,
                }
            })

            with patch("app.services._03_event_identification.PromptTemplate") as mock_template:
                mock_template.return_value.__or__ = MagicMock(
                    return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
                )
                result = await service._propose_new_events_with_llm(
                    text="CEO resigned suddenly",
                    unmatched_tickers={"AAPL": {"primary_event_category": "COMPANY_EVENT"}},
                )

    assert "AAPL" in result
    assert result["AAPL"]["proposed_event_name"] == "CEO_DEPARTURE"


@pytest.mark.asyncio
async def test_propose_enforces_category_consistency(service):
    """LLM returns wrong category → corrected to match input."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value={
        "AAPL": {
            "primary_event_category": "EXTERNAL_EVENT",  # wrong — input was COMPANY_EVENT
            "proposed_event_name": "NEW_PRODUCT",
            "proposed_description": "Product launch",
            "meaning": "New product",
            "confidence": 0.8,
        }
    })

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template:
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        result = await service._propose_new_events_with_llm(
            text="Apple launches new product",
            unmatched_tickers={"AAPL": {"primary_event_category": "COMPANY_EVENT"}},
        )

    assert result["AAPL"]["primary_event_category"] == "COMPANY_EVENT"


@pytest.mark.asyncio
async def test_propose_retries_on_failure_then_succeeds(service):
    """First ainvoke raises, second succeeds."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(side_effect=[
        Exception("timeout"),
        {"AAPL": {"primary_event_category": "COMPANY_EVENT", "proposed_event_name": "X", "meaning": "y", "confidence": 0.8}},
    ])

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template, \
         patch("app.services._03_event_identification.asyncio.sleep", new=AsyncMock()):
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        result = await service._propose_new_events_with_llm(
            text="text",
            unmatched_tickers={"AAPL": {"primary_event_category": "COMPANY_EVENT"}},
        )

    assert "AAPL" in result


@pytest.mark.asyncio
async def test_propose_all_retries_fail_returns_empty(service):
    """All LLM attempts fail → returns {}."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(side_effect=Exception("always fails"))

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template, \
         patch("app.services._03_event_identification.asyncio.sleep", new=AsyncMock()):
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        result = await service._propose_new_events_with_llm(
            text="text",
            unmatched_tickers={"AAPL": {"primary_event_category": "COMPANY_EVENT"}},
        )

    assert result == {}


# ─── _analyse_events_with_llm() ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyse_no_llm_returns_empty(service):
    service.llm = None
    result = await service._analyse_events_with_llm(
        ticker_inputs={"AAPL": {}},
        event_category_map={"COMPANY_EVENT": ["EARNINGS_BEAT"]},
    )
    assert result == {}


@pytest.mark.asyncio
async def test_analyse_empty_ticker_inputs_returns_empty(service):
    result = await service._analyse_events_with_llm(
        ticker_inputs={},
        event_category_map={"COMPANY_EVENT": ["EARNINGS_BEAT"]},
    )
    assert result == {}


@pytest.mark.asyncio
async def test_analyse_success(service):
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value={
        "tickers": {
            "AAPL": {
                "primary_event_category": "COMPANY_EVENT",
                "event_type": "EARNINGS_BEAT",
                "event_description": "Apple beat Q4 earnings",
            }
        }
    })

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template:
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        result = await service._analyse_events_with_llm(
            ticker_inputs={"AAPL": {"primary_event_category": "COMPANY_EVENT", "event_description": "beat earnings"}},
            event_category_map={"COMPANY_EVENT": ["EARNINGS_BEAT"]},
        )

    assert result["tickers"]["AAPL"]["event_type"] == "EARNINGS_BEAT"


@pytest.mark.asyncio
async def test_analyse_invalid_structure_retries_then_returns_inputs(service):
    """LLM returns non-dict → retries, all fail → returns ticker_inputs."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value="not a dict")  # invalid every time

    ticker_inputs = {"AAPL": {"primary_event_category": "COMPANY_EVENT"}}

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template, \
         patch("app.services._03_event_identification.asyncio.sleep", new=AsyncMock()):
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        result = await service._analyse_events_with_llm(
            ticker_inputs=ticker_inputs,
            event_category_map={"COMPANY_EVENT": ["EARNINGS_BEAT"]},
        )

    assert result == ticker_inputs


# ─── _identify_primary_tickers() ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_identify_no_llm_returns_ticker_metadata(service):
    service.llm = None
    metadata = {"AAPL": {"name": "Apple"}}
    result = await service._identify_primary_tickers("Apple bought back stock", metadata)
    assert result == metadata


@pytest.mark.asyncio
async def test_identify_investor_action_sets_event_type(service):
    """INVESTOR_ACTION tickers bypass taxonomy and get event_type set directly."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value={
        "primary_tickers": ["AAPL"],
        "tickers": {
            "AAPL": {
                "primary_event_category": "INVESTOR_ACTION",
                "event_description": "Bought 100 shares",
            }
        },
    })

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template:
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        # _analyse_events_with_llm should NOT be called for INVESTOR_ACTION
        service._analyse_events_with_llm = AsyncMock(return_value={"tickers": {}})

        metadata = {"AAPL": {}}
        result = await service._identify_primary_tickers("I bought AAPL today", metadata)

    assert result["AAPL"]["event_type"] == "INVESTOR_ACTION"
    assert result["AAPL"]["event_description"] == "Bought 100 shares"
    service._analyse_events_with_llm.assert_not_called()


@pytest.mark.asyncio
async def test_identify_investor_opinion_sets_event_type(service):
    """INVESTOR_OPINION tickers bypass taxonomy."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value={
        "primary_tickers": ["MSFT"],
        "tickers": {
            "MSFT": {
                "primary_event_category": "INVESTOR_OPINION",
                "event_description": "Bullish on MSFT",
            }
        },
    })

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template:
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        service._analyse_events_with_llm = AsyncMock(return_value={"tickers": {}})

        metadata = {"MSFT": {}}
        result = await service._identify_primary_tickers("I think MSFT is a buy", metadata)

    assert result["MSFT"]["event_type"] == "INVESTOR_OPINION"
    service._analyse_events_with_llm.assert_not_called()


@pytest.mark.asyncio
async def test_identify_company_event_calls_analyse(service):
    """COMPANY_EVENT tickers go to _analyse_events_with_llm."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value={
        "primary_tickers": ["AAPL"],
        "tickers": {
            "AAPL": {
                "primary_event_category": "COMPANY_EVENT",
                "event_description": "CEO resigned",
            }
        },
    })

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template:
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        service._analyse_events_with_llm = AsyncMock(return_value={
            "tickers": {
                "AAPL": {
                    "primary_event_category": "COMPANY_EVENT",
                    "event_type": "EARNINGS_BEAT",
                    "event_description": "CEO resigned",
                }
            }
        })

        metadata = {"AAPL": {}}
        result = await service._identify_primary_tickers("Apple CEO resigned", metadata)

    service._analyse_events_with_llm.assert_called_once()
    assert result["AAPL"]["event_type"] == "EARNINGS_BEAT"


@pytest.mark.asyncio
async def test_identify_unmatched_ticker_calls_propose_and_adds_event(service):
    """event_type=None after analyse → propose called, high confidence → added to event_list."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value={
        "primary_tickers": ["AAPL"],
        "tickers": {
            "AAPL": {
                "primary_event_category": "COMPANY_EVENT",
                "event_description": "Unusual activity",
            }
        },
    })

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template:
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        service._analyse_events_with_llm = AsyncMock(return_value={
            "tickers": {
                "AAPL": {
                    "primary_event_category": "COMPANY_EVENT",
                    "event_type": None,
                    "event_description": None,
                }
            }
        })
        service._propose_new_events_with_llm = AsyncMock(return_value={
            "AAPL": {
                "primary_event_category": "COMPANY_EVENT",
                "proposed_event_name": "CEO_DEPARTURE",
                "proposed_description": "CEO left the company",
                "meaning": "Leadership change",
                "confidence": 0.9,
            }
        })

        metadata = {"AAPL": {}}
        result = await service._identify_primary_tickers("Apple CEO left", metadata)

    service._propose_new_events_with_llm.assert_called_once()
    assert "CEO_DEPARTURE" in service.event_list
    assert service.neweventcount == 1
    assert result["AAPL"]["event_type"] == "CEO_DEPARTURE"
    assert result["AAPL"]["event_description"] == "CEO left the company"


@pytest.mark.asyncio
async def test_identify_proposal_low_confidence_not_added(service):
    """Proposal confidence < 0.75 → event NOT added to event_list."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value={
        "primary_tickers": ["AAPL"],
        "tickers": {
            "AAPL": {
                "primary_event_category": "COMPANY_EVENT",
                "event_description": "vague activity",
            }
        },
    })

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template:
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        service._analyse_events_with_llm = AsyncMock(return_value={
            "tickers": {
                "AAPL": {
                    "primary_event_category": "COMPANY_EVENT",
                    "event_type": None,
                    "event_description": None,
                }
            }
        })
        service._propose_new_events_with_llm = AsyncMock(return_value={
            "AAPL": {
                "primary_event_category": "COMPANY_EVENT",
                "proposed_event_name": "VAGUE_EVENT",
                "proposed_description": "vague",
                "meaning": "unclear",
                "confidence": 0.5,  # below threshold
            }
        })

        initial_count = service.neweventcount
        metadata = {"AAPL": {}}
        await service._identify_primary_tickers("vague Apple activity", metadata)

    assert service.neweventcount == initial_count
    assert "VAGUE_EVENT" not in service.event_list


@pytest.mark.asyncio
async def test_identify_ticker_not_in_metadata_skipped(service):
    """LLM returns a ticker not in the original metadata → ignored."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value={
        "primary_tickers": ["GOOG"],  # not in metadata
        "tickers": {
            "GOOG": {
                "primary_event_category": "COMPANY_EVENT",
                "event_description": "Google layoffs",
            }
        },
    })

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template:
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        service._analyse_events_with_llm = AsyncMock(return_value={"tickers": {}})

        metadata = {"AAPL": {}}  # only AAPL
        result = await service._identify_primary_tickers("Google had layoffs", metadata)

    assert "GOOG" not in result


@pytest.mark.asyncio
async def test_identify_all_retries_fail_returns_metadata(service):
    """All LLM attempts fail → returns ticker_metadata as-is."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(side_effect=Exception("LLM error"))

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template, \
         patch("app.services._03_event_identification.asyncio.sleep", new=AsyncMock()):
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        metadata = {"AAPL": {"name": "Apple"}}
        result = await service._identify_primary_tickers("Apple news", metadata)

    assert result == metadata


@pytest.mark.asyncio
async def test_identify_skip_primary_filter_uses_different_prompt(service):
    """skip_primary_filter=True uses a simpler prompt (no primary_tickers field in response)."""
    fake_chain = MagicMock()
    fake_chain.ainvoke = AsyncMock(return_value={
        # skip_primary_filter returns just tickers dict, no primary_tickers
        "tickers": {
            "AAPL": {
                "primary_event_category": "INVESTOR_ACTION",
                "event_description": "Bought 200 shares",
            }
        }
    })

    with patch("app.services._03_event_identification.PromptTemplate") as mock_template:
        mock_template.return_value.__or__ = MagicMock(
            return_value=MagicMock(__or__=MagicMock(return_value=fake_chain))
        )
        service._analyse_events_with_llm = AsyncMock(return_value={"tickers": {}})

        metadata = {"AAPL": {}}
        result = await service._identify_primary_tickers(
            "Bought 200 AAPL shares", metadata, skip_primary_filter=True
        )

    # Should process INVESTOR_ACTION directly
    assert result["AAPL"]["event_type"] == "INVESTOR_ACTION"


# ─── analyse_event() ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_analyse_event_no_metadata_skip_false(service):
    """No 'ticker' in post_metadata → skip_primary_filter=False."""
    service._identify_primary_tickers = AsyncMock(return_value={"AAPL": {"event_type": "EARNINGS_BEAT"}})

    post = {
        "content": {"clean_combined_withurl": "Apple earnings beat"},
        "ticker_metadata": {"AAPL": {}},
        "metadata": {"source": "reddit"},
    }
    result = await service.analyse_event(post)

    service._identify_primary_tickers.assert_called_once_with(
        "Apple earnings beat", {"AAPL": {}}, skip_primary_filter=False
    )
    assert result["ticker_metadata"]["AAPL"]["event_type"] == "EARNINGS_BEAT"


@pytest.mark.asyncio
async def test_analyse_event_with_ticker_in_metadata_skip_true(service):
    """'ticker' key in post_metadata → skip_primary_filter=True."""
    service._identify_primary_tickers = AsyncMock(return_value={"AAPL": {"event_type": "INVESTOR_ACTION"}})

    post = {
        "content": {"clean_combined_withurl": "Bought AAPL"},
        "ticker_metadata": {"AAPL": {}},
        "metadata": {"ticker": "AAPL", "source": "twitter"},
    }
    result = await service.analyse_event(post)

    service._identify_primary_tickers.assert_called_once_with(
        "Bought AAPL", {"AAPL": {}}, skip_primary_filter=True
    )
    assert result["ticker_metadata"]["AAPL"]["event_type"] == "INVESTOR_ACTION"


@pytest.mark.asyncio
async def test_analyse_event_no_post_metadata(service):
    """post_metadata missing entirely → skip_primary_filter=False."""
    service._identify_primary_tickers = AsyncMock(return_value={"AAPL": {}})

    post = {
        "content": {"clean_combined_withurl": "Apple news"},
        "ticker_metadata": {"AAPL": {}},
    }
    await service.analyse_event(post)

    _, kwargs = service._identify_primary_tickers.call_args
    assert kwargs["skip_primary_filter"] is False


@pytest.mark.asyncio
async def test_analyse_event_returns_updated_post(service):
    """analyse_event returns the full post dict with ticker_metadata updated."""
    service._identify_primary_tickers = AsyncMock(return_value={"AAPL": {"event_type": "RATE_HIKE"}})

    post = {
        "content": {"clean_combined_withurl": "Fed raised rates"},
        "ticker_metadata": {"AAPL": {}},
        "metadata": {},
    }
    result = await service.analyse_event(post)

    assert result is post
    assert result["ticker_metadata"] == {"AAPL": {"event_type": "RATE_HIKE"}}
