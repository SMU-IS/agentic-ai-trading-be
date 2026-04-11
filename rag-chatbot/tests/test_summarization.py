import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, RemoveMessage
from app.services.graph.chat_workflow import ChatWorkflow
from app.services.graph.state import AgentState

@pytest.fixture
def mock_llm():
    llm = AsyncMock()
    # bind_tools is a synchronous method in LangChain
    mock_bound = AsyncMock()
    llm.bind_tools = MagicMock(return_value=mock_bound)
    return llm

@pytest.mark.asyncio
async def test_summarize_no_delete(mock_llm):
    """
    Test that _summarize_conversation does NOT delete messages
    and correctly updates summary and last_summarized_id.
    """
    workflow = ChatWorkflow(llm=mock_llm, tools=[], system_prompt="test")
    
    # Create 15 messages (above threshold of 12)
    messages = [HumanMessage(content=f"msg {i}", id=f"id_{i}") for i in range(15)]
    
    state = AgentState(
        messages=messages,
        summary="",
        last_summarized_id=None
    )
    
    # Mock LLM response for summarization
    mock_llm.ainvoke.return_value = MagicMock(content="New Summary")
    
    # Execute summarization
    result = await workflow._summarize_conversation(state)
    
    # Assertions
    assert "summary" in result
    assert result["summary"] == "New Summary"
    assert "last_summarized_id" in result
    # It should have summarized everything except the last 6 messages
    # to_summarize = messages[0 : -6] -> messages[0:9]
    # last_summarized_id should be messages[8].id
    assert result["last_summarized_id"] == "id_8"
    
    # CRITICAL: Ensure no RemoveMessage in result["messages"] (it shouldn't even have "messages" key now)
    assert "messages" not in result

@pytest.mark.asyncio
async def test_summarize_incremental(mock_llm):
    """
    Test that summarization is incremental using last_summarized_id.
    """
    workflow = ChatWorkflow(llm=mock_llm, tools=[], system_prompt="test")
    
    # Initial state with previous summary
    messages = [HumanMessage(content=f"msg {i}", id=f"id_{i}") for i in range(15)]
    
    state = AgentState(
        messages=messages,
        summary="Old Summary",
        last_summarized_id="id_5" # Already summarized up to id_5
    )
    
    mock_llm.ainvoke.return_value = MagicMock(content="Updated Summary")
    
    # Execute
    result = await workflow._summarize_conversation(state)
    
    # Check what was sent to LLM for summarization
    # start_idx should be 6 (index of id_5 is 5, +1 = 6)
    # to_summarize should be messages[6 : -6] -> messages[6:9] (id_6, id_7, id_8)
    call_args = mock_llm.ainvoke.call_args[0][0]
    summarized_contents = [m.content for m in call_args if isinstance(m, HumanMessage)]
    
    assert "msg 6" in summarized_contents
    assert "msg 8" in summarized_contents
    assert "msg 5" not in summarized_contents # Already summarized
    assert "msg 9" not in summarized_contents # In the KEEP window
    
    assert result["summary"] == "Updated Summary"
    assert result["last_summarized_id"] == "id_8"

@pytest.mark.asyncio
async def test_call_model_windowing(mock_llm):
    """
    Test that _call_model only sends the last 6 messages when a summary exists.
    """
    workflow = ChatWorkflow(llm=mock_llm, tools=[], system_prompt="test")
    
    messages = [HumanMessage(content=f"msg {i}", id=f"id_{i}") for i in range(20)]
    state = AgentState(
        messages=messages,
        summary="Context Summary",
        last_summarized_id="id_13"
    )
    
    config = {"configurable": {"thread_id": "test"}, "metadata": {"user_id": "user123"}}
    
    await workflow._call_model(state, config)
    
    # Check messages sent to ainvoke
    # SystemMessage + last 6 messages
    # Since llm_with_tools was set during __init__, it's mock_llm.bind_tools.return_value
    mock_bound = mock_llm.bind_tools.return_value
    sent_messages = mock_bound.ainvoke.call_args[0][0]
    # 1 System + 6 windowed = 7
    assert len(sent_messages) == 7
    assert sent_messages[1].content == "msg 14"
    assert sent_messages[-1].content == "msg 19"

@pytest.mark.asyncio
async def test_call_model_windowing_safe_boundary(mock_llm):
    """
    Test that _call_model expands the window to avoid starting with a ToolMessage.
    """
    from langchain_core.messages import ToolMessage
    workflow = ChatWorkflow(llm=mock_llm, tools=[], system_prompt="test")
    
    # 0-13: Some messages
    # 14: Human
    # 15: AI (tool call)
    # 16: Tool result
    # 17: AI (response)
    # 18: Human (new query)
    # 19: AI (tool call)
    # 20: Tool result
    messages = [HumanMessage(content=f"msg {i}", id=f"id_{i}") for i in range(15)]
    messages.append(AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "t1"}], id="ai_tool"))
    messages.append(ToolMessage(content="result", tool_call_id="t1", id="tool_res"))
    messages.append(AIMessage(content="Final", id="ai_final"))
    messages.append(HumanMessage(content="Next", id="human_next"))
    messages.append(AIMessage(content="", tool_calls=[{"name": "t2", "args": {}, "id": "t2"}], id="ai_tool2"))
    messages.append(ToolMessage(content="result2", tool_call_id="t2", id="tool_res2"))
    
    # Total messages: 15 + 6 = 21
    # messages[-6] would be id="ai_tool" (index 15)
    # But if it were index 16 (ToolMessage), it should expand.
    
    state = AgentState(
        messages=messages,
        summary="Context Summary",
        last_summarized_id="id_10"
    )
    
    config = {"configurable": {"thread_id": "test"}, "metadata": {"user_id": "user123"}}
    
    await workflow._call_model(state, config)
    
    mock_bound = mock_llm.bind_tools.return_value
    sent_messages = mock_bound.ainvoke.call_args[0][0]
    
    # The last 6 messages are: ai_tool, tool_res, ai_final, human_next, ai_tool2, tool_res2
    # This window is actually "safe" because it starts with an AIMessage (though with tool_calls)
    # Our logic: starts with AI with tool_calls -> expand back.
    # So it should expand to messages[14] (Human "Next")
    assert sent_messages[1].content == "msg 14"
