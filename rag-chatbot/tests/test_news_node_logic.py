import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage
from app.services.ai_agent.nodes.general_news import general_news_node
from app.schemas.chat import GeneralNews

@pytest.mark.asyncio
async def test_general_news_node_extraction_today():
    """Test that general_news_node extracts dates for 'today'."""
    llm = MagicMock()
    
    # Mock the structured LLM for parameter extraction
    mock_extracted = GeneralNews(
        query="how was the market today",
        tickers=[],
        start_date="2026-04-07T00:00:00",
        end_date="2026-04-07T23:59:59"
    )
    
    structured_llm_mock = MagicMock()
    structured_llm_mock.ainvoke = AsyncMock(return_value=mock_extracted)
    llm.with_structured_output.return_value = structured_llm_mock
    
    # Mock the final LLM response for formatting
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="The market was bullish today."))
    
    state = {
        "messages": [HumanMessage(content="how was the market today")],
        "query": "how was the market today",
    }
    
    # Mock the tool call
    with patch("app.services.tools.general_news.get_general_news") as mock_tool:
        mock_tool.ainvoke = AsyncMock(return_value={"context": "Raw news data", "results": []})
        
        result = await general_news_node(state, llm)
        
        # Verify tool was called with date parameters
        mock_tool.ainvoke.assert_called_once()
        args = mock_tool.ainvoke.call_args[0][0]
        assert args["start_date"] == "2026-04-07T00:00:00"
        assert args["end_date"] == "2026-04-07T23:59:59"
        assert args["tickers"] == []
        
        # Verify final message
        assert result["messages"][0].content == "The market was bullish today."

@pytest.mark.asyncio
async def test_general_news_node_extraction_ticker():
    """Test that general_news_node extracts tickers and calls the right endpoint logic."""
    llm = MagicMock()
    
    # Mock extraction for a specific ticker
    mock_extracted = GeneralNews(
        query="what is the news for AAPL",
        tickers=["AAPL"],
        start_date=None,
        end_date=None
    )
    
    structured_llm_mock = MagicMock()
    structured_llm_mock.ainvoke = AsyncMock(return_value=mock_extracted)
    llm.with_structured_output.return_value = structured_llm_mock
    
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="AAPL is doing great."))
    
    state = {
        "messages": [HumanMessage(content="what is the news for AAPL")],
        "query": "what is the news for AAPL",
    }
    
    with patch("app.services.tools.general_news.get_general_news") as mock_tool:
        mock_tool.ainvoke = AsyncMock(return_value={"context": "AAPL news data", "results": []})
        
        await general_news_node(state, llm)
        
        # Verify tool was called with ticker
        mock_tool.ainvoke.assert_called_once()
        args = mock_tool.ainvoke.call_args[0][0]
        assert args["tickers"] == ["AAPL"]
        assert args["start_date"] is None
