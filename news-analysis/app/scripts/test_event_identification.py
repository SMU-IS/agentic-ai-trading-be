from unittest.mock import patch

import pytest
from app.schemas.event_models import NewsPayload

# Adjust this import to match your actual folder structure
from app.services._02_event_identification import EventIdentifierService


@pytest.fixture
def service():
    """
    Returns an instance of the service with mocked config
    """

    # We mock the config values to avoid needing a real .env file for tests
    with patch("app.core.config.env_config") as mock_config:
        mock_config.llm_provider = "ollama"
        mock_config.large_language_model = "llama3"
        mock_config.ollama_base_url = "http://localhost:11434"

        # return the initialized service
        return EventIdentifierService()


@pytest.fixture
def earnings_payload():
    """
    A payload that SHOULD trigger the Rule-Based logic
    """

    return NewsPayload(
        id="123",
        headline="Apple reports Q4 Earnings Release",
        content="Revenue exceeded expectations.",
        source="Bloomberg",
    )


@pytest.fixture
def vague_payload():
    """
    A payload that SHOULD fail rules and trigger the LLM
    """

    return NewsPayload(
        id="456",
        headline="Tech Giant Faces Uncertain Future",
        content="Insiders whisper about a secret project that could change the industry.",
        source="TechCrunch",
    )


@pytest.mark.asyncio
async def test_rule_based_detection(service, earnings_payload):
    """
    Test 1: Verify that explicit keywords trigger the rule-based path
    WITHOUT calling the LLM.
    """

    with patch.object(service, "_analyse_with_llm") as mock_llm_method:
        response = await service.process_event(earnings_payload)

        # Assertions
        assert response.event_detected is True
        assert response.method == "rule-based"
        assert response.event_type == "earnings"
        assert response.confidence == 0.95

        mock_llm_method.assert_not_called()


@pytest.mark.asyncio
async def test_llm_fallback_detection(service, vague_payload):
    """
    Test 2: Verify that when rules fail, the service calls the LLM.
    """

    # Mock the chain.invoke to return a "detected" event
    mock_llm_result = {
        "is_event": True,
        "event_category": "product_launch",
        "confidence": 0.85,
        "reasoning": "Implied product launch based on rumors.",
    }

    with patch.object(service, "_analyse_with_llm") as mock_method:
        # Define what the mocked LLM returns (Pydantic object)
        from app.schemas.event_models import LLMEventResult

        mock_method.return_value = LLMEventResult(**mock_llm_result)

        response = await service.process_event(vague_payload)

        # Assertions
        assert response.event_detected is True
        assert response.method == "llm-ollama"  # Should match your config
        assert response.event_type == "product_launch"

        # Verify LLM was actually called
        mock_method.assert_called_once()


@pytest.mark.asyncio
async def test_no_event_found(service):
    """
    Test 3: Verify behavior when neither Rules nor LLM find anything.
    """

    boring_payload = NewsPayload(
        id="789",
        headline="Weather is nice today",
        content="Sunny skies expected all week.",
    )

    mock_llm_result = {
        "is_event": False,
        "event_category": "none",
        "confidence": 0.1,
        "reasoning": "Weather is not financial news.",
    }

    with patch.object(service, "_analyse_with_llm") as mock_method:
        from app.schemas.event_models import LLMEventResult

        mock_method.return_value = LLMEventResult(**mock_llm_result)

        response = await service.process_event(boring_payload)

        assert response.event_detected is False
        assert response.method == "hybrid"
        assert "No significant event" in response.summary
