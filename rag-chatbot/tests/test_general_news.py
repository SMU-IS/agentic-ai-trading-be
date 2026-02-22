
import pytest
import respx
import httpx
from app.services.tools.general_news import get_general_news

@pytest.mark.asyncio
@respx.mock
async def test_get_general_news_success():
    # Mock URL
    url = "http://testserver/news"
    
    # Mock environment config
    with respx.mock:
        respx.post("http://testserver/news").mock(return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"headline": "Apple news", "content_preview": "Apple did something."},
                    {"headline": "Tesla news", "content_preview": "Tesla did something else."}
                ]
            }
        ))
        
        from app.core.config import env_config
        env_config.qdrant_retrieval_query_url = "http://testserver/news"

        result = await get_general_news.ainvoke({"query": "test query", "tickers": ["AAPL", "TSLA"]})

        assert result["results"] == [
            {"headline": "Apple news", "content_preview": "Apple did something."},
            {"headline": "Tesla news", "content_preview": "Tesla did something else."}
        ]
        assert "Apple news" in result["context"]
        assert "Tesla news" in result["context"]

@pytest.mark.asyncio
@respx.mock
async def test_get_general_news_no_results():
    # Mock environment config
    from app.core.config import env_config
    env_config.qdrant_retrieval_query_url = "http://testserver/news"

    respx.post("http://testserver/news").mock(return_value=httpx.Response(
        200,
        json={"results": []}
    ))

    result = await get_general_news.ainvoke({"query": "test query", "tickers": ["AAPL"]})

    assert result["results"] == []
    assert result["context"] == "No relevant news found for the requested tickers."

@pytest.mark.asyncio
@respx.mock
async def test_get_general_news_api_error():
    # Mock environment config
    from app.core.config import env_config
    env_config.qdrant_retrieval_query_url = "http://testserver/news"

    respx.post("http://testserver/news").mock(return_value=httpx.Response(500))

    result = await get_general_news.ainvoke({"query": "test query", "tickers": ["AAPL"]})

    assert result["results"] == []
    assert "API Error: 500" in result["context"]

@pytest.mark.asyncio
@respx.mock
async def test_get_general_news_network_error():
    # Mock environment config
    from app.core.config import env_config
    env_config.qdrant_retrieval_query_url = "http://testserver/news"

    respx.post("http://testserver/news").mock(side_effect=httpx.RequestError("Connection failed"))

    result = await get_general_news.ainvoke({"query": "test query", "tickers": ["AAPL"]})

    assert result["results"] == []
    assert "Network Error" in result["context"]
