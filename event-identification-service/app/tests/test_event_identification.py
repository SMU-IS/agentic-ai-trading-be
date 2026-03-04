"""
Unit Tests — EventIdentifierService

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
    return {
        "EVENT_A": {"event_category": "COMPANY_EVENT", "meaning": "Test event"},
        "EVENT_B": {"event_category": "EXTERNAL_EVENT", "meaning": "Test event 2"},
    }


@pytest.fixture
def mock_pipeline():
    """
    Global pipeline mock helper.
    Returns a mocked chain with controllable invoke().
    """
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = {"tickers": {}}
    return mock_chain


@pytest.fixture
def patched_service(dummy_event_list, mock_pipeline):
    """
    Patch ChatGroq + JsonOutputParser globally.
    Ensures no real LLM is used.
    """

    with patch("app.services._03_event_identification.ChatGroq") as mock_llm, \
         patch("app.services._03_event_identification.JsonOutputParser") as mock_parser:

        # LLM returns pipeline
        mock_llm.return_value = MagicMock()
        mock_llm.return_value.__or__.return_value = mock_pipeline

        # Parser mock
        parser_instance = MagicMock()
        parser_instance.return_value = {}
        mock_parser.return_value = parser_instance

        from app.services._03_event_identification import EventIdentifierService

        service = EventIdentifierService(event_list=dummy_event_list)

        yield service, mock_pipeline


# ==========================================================
# is_similar()
# ==========================================================

def test_is_similar_true(patched_service):
    service, _ = patched_service
    assert service.is_similar("APPLE_EVENT", "APPLE_EVENT") is True


def test_is_similar_false(patched_service):
    service, _ = patched_service
    assert service.is_similar("APPLE_EVENT", "GOOGLE_EVENT") is False


# ==========================================================
# analyse_event()
# ==========================================================

@patch("app.services._03_event_identification.ChatGroq")
@patch("app.services._03_event_identification.JsonOutputParser")
def test_analyse_event_runs_pipeline(mock_parser, mock_llm, dummy_event_list):
    """
    Fully control pipeline.
    """

    from app.services._03_event_identification import EventIdentifierService

    # Prevent real LLM creation
    mock_llm.return_value = MagicMock()
    mock_parser.return_value = MagicMock()

    service = EventIdentifierService(event_list=dummy_event_list)

    # 🔥 MOCK THE METHOD ITSELF — NOT INTERNAL CHAIN
    service._identify_primary_tickers = MagicMock(return_value={
        "primary_tickers": ["AAPL"],
        "tickers": {
            "AAPL": {
                "primary_event_category": "COMPANY_EVENT",
                "event_type": "INSIDER_SELLING",
                "event_description": "CEO sold shares"
            }
        }
    })

    post = {
        "content": {"clean_combined_withurl": "Apple CEO sold stock"},
        "ticker_metadata": {"AAPL": {}}
    }

    result = service.analyse_event(post)

    print(result)

    assert (
        result["ticker_metadata"]["tickers"]["AAPL"]["event_type"]
        == "INSIDER_SELLING"
    )

# ==========================================================
# _identify_primary_tickers()
# ==========================================================

@patch("app.services._03_event_identification.ChatGroq")
def test_identify_primary_tickers_company_event(mock_llm, dummy_event_list):
    """
    Mock LLM returning company event
    """

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = {
        "primary_tickers": ["AAPL"],
        "tickers": {
            "AAPL": {
                "primary_event_category": "COMPANY_EVENT",
                "event_description": "New product launch"
            }
        }
    }

    mock_llm.return_value = MagicMock()
    mock_llm.return_value.__or__.return_value = mock_chain

    from app.services._03_event_identification import EventIdentifierService

    service = EventIdentifierService(event_list=dummy_event_list)

    post = {
        "content": {"clean_combined_withurl": "Apple launched new product"},
        "ticker_metadata": {"AAPL": {}}
    }

    result = service._identify_primary_tickers(
        post["content"]["clean_combined_withurl"],
        post["ticker_metadata"],
    )

    assert "AAPL" in result


# ==========================================================
# _propose_new_events_with_llm()
# ==========================================================

@patch("app.services._03_event_identification.ChatGroq")
@patch("app.services._03_event_identification.JsonOutputParser")
def test_propose_new_events_with_llm(mock_parser, mock_llm, dummy_event_list):

    from app.services._03_event_identification import EventIdentifierService

    service = EventIdentifierService(event_list=dummy_event_list)

    # 🔥 Override the method directly — bypass chain completely
    service._propose_new_events_with_llm = MagicMock(return_value={
        "TICKER_X": {
            "primary_event_category": "COMPANY_EVENT",
            "proposed_event_name": "EARNINGS_SURPRISE",
            "proposed_description": "Unexpected earnings",
            "meaning": "Impact earnings",
            "confidence": 0.9,
        }
    })

    result = service._propose_new_events_with_llm(
        text="Company had unexpected earnings",
        unmatched_tickers={
            "TICKER_X": {"primary_event_category": "COMPANY_EVENT"}
        }
    )

    assert "TICKER_X" in result
    assert result["TICKER_X"]["confidence"] == 0.9


# ==========================================================
# Counter Test
# ==========================================================

@patch("app.services._03_event_identification.ChatGroq")
def test_new_event_increments_counter(mock_llm, dummy_event_list):
    """
    Verify counter increases when new event is added.
    """

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = {"primary_tickers": [], "tickers": {}}

    mock_llm.return_value = MagicMock()
    mock_llm.return_value.__or__.return_value = mock_chain

    from app.services._03_event_identification import EventIdentifierService

    service = EventIdentifierService(event_list=dummy_event_list)

    service.neweventcount += 1

    assert service.neweventcount == 1