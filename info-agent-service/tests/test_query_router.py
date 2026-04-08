import json
from unittest.mock import MagicMock


def test_query_endpoint(client, mock_info_agent_service):
    request_data = {"query": "how to trade", "session_id": "test_session"}

    # Define a custom mock ainvoke to yield values
    async def mock_ainvoke(question, session_id):
        yield {"status": "Searching knowledge base..."}
        yield {"token": "trading is easy"}

    mock_info_agent_service.ainvoke = mock_ainvoke

    response = client.post("/query", json=request_data)

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    # Process SSE events
    lines = response.text.strip().split("\n\n")
    data = [line.replace("data: ", "") for line in lines]

    assert json.loads(data[0]) == {"status": "Searching knowledge base..."}
    assert json.loads(data[1]) == {"token": "trading is easy"}
    assert data[2] == "[DONE]"


def test_history_endpoint(client, mock_info_agent_service):
    # Mock history messages
    mock_history = MagicMock()

    class MockMessage:
        def __init__(self, type, content):
            self.type = type
            self.content = content

    mock_history.messages = [
        MockMessage("human", "hello"),
        MockMessage("ai", "hi there"),
    ]
    mock_info_agent_service.get_session_history.return_value = mock_history

    response = client.get("/history/test_session")

    assert response.status_code == 200
    history = response.json()["history"]
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "hello"}
    assert history[1] == {"role": "assistant", "content": "hi there"}


def test_history_endpoint_error(client, mock_info_agent_service):
    # Mock error in service
    mock_info_agent_service.get_session_history.side_effect = Exception(
        "Database error"
    )

    response = client.get("/history/test_session")
    assert response.status_code == 500
    assert response.json()["detail"] == "Database error"
