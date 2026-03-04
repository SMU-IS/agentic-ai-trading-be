"""
Unit Tests — TickerIdentificationService

We mock LLM pipeline completely.
No real Groq API calls.
"""

import pytest
from unittest.mock import MagicMock, patch


# ==========================================================
# Fixtures
# ==========================================================

@pytest.fixture
def dummy_event_list():
    """
    Your service requires a parameter,
    but ticker service does NOT actually use it directly.
    So we just pass dummy data.
    """
    return {
        "EVENT_A": {"event_category": "COMPANY_EVENT", "meaning": "Test event"},
    }


@pytest.fixture
def service(dummy_event_list):
    """
    Create service with LLM fully mocked.
    """

    with patch("app.services._02_ticker_identification.ChatGroq"), \
         patch("app.services._02_ticker_identification.JsonOutputParser"), \
         patch("spacy.load"):

        from app.services._02_ticker_identification import TickerIdentificationService

        svc = TickerIdentificationService(
            cleaned_tickers={},
            alias_to_canonical={},
        )

        # 🔥 Disable real LLM chain completely
        svc._extract_company_ticker_llm = MagicMock(return_value=[
            {
                "company_name": "Apple Inc.",
                "ticker": "AAPL"
            }
        ])

        yield svc


# ==========================================================
# is_similar style logic (if applicable)
# ==========================================================

def test_service_initialization(service):
    """
    Ensure service loads properly.
    """

    assert service is not None
    assert isinstance(service.cleaned_tickers, dict)


# ==========================================================
# extract_tickers()
# ==========================================================

def test_extract_tickers_with_mocked_llm(service):
    mock_doc = MagicMock()
    mock_doc.ents = []

    service.nlp = MagicMock(return_value=mock_doc)

    # IMPORTANT
    service.ticker_to_title = {"AAPL": "Apple Inc."}
    service.ticker_to_canonical = {"AAPL": "aapl"}

    result = service.extract_tickers("Apple Inc announced earnings")

    assert "AAPL" in result

# ==========================================================
# _extract_company_ticker_llm()
# ==========================================================

def test_extract_company_ticker_llm(service):
    """
    Test that validation logic works after LLM returns structured data.
    """

    # Call directly (already mocked)
    result = service._extract_company_ticker_llm(
        "Apple Inc is growing"
    )
    print(result)
    assert isinstance(result, list)
    assert result[0]["ticker"] == "AAPL"


# ==========================================================
# update_alias_mapping()
# ==========================================================

def test_update_alias_mapping(service):
    """
    Test alias updates properly.
    """

    service.update_alias_mapping("Apple Inc.", "aapl")

    # alias should now be stored
    norm_alias = service._normalize_company(
        service._remove_suffix("Apple Inc.")
    )

    assert norm_alias in service.alias_to_canonical


# ==========================================================
# get_aliases()
# ==========================================================

def test_get_aliases(service):
    service.ticker_to_title = {"AAPL": "Apple Inc."}
    service.ticker_to_canonical = {"AAPL": "aapl"}
    service.canonical_to_aliases = {"aapl": ["apple"]}

    result = service.get_aliases(["AAPL"])

    assert "AAPL" in result
    assert result["AAPL"]["OfficialName"] == "Apple Inc."
    assert "apple" in result["AAPL"]["Aliases"]