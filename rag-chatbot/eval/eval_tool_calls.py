import asyncio
import json
import logging
import os

from app.core.config import env_config
from app.core.constant import LLMProviders
from app.providers.llm.registry import get_strategy
from app.services.agent_bot_service import AgentBotService
from app.services.bot_memory import BotMemory
from langsmith import aevaluate
from psycopg_pool import AsyncConnectionPool

logging.basicConfig(level=logging.INFO)


os.environ["LANGSMITH_API_KEY"] = env_config.langsmith_api_key
os.environ["LANGSMITH_TRACING"] = env_config.langsmith_tracing


service: AgentBotService = None


async def target(inputs: dict):
    tools_called = []
    final_response = []

    async for chunk in service.invoke_agent(
        query=inputs["query"],
        order_id=inputs.get("order_id"),
        user_id="eval-user",
        session_id=f"eval-{inputs['query'][:15]}",
    ):
        if '"status"' in chunk and "Calling" in chunk:
            data = json.loads(chunk.replace("data: ", ""))
            tool_name = data["status"].replace("Calling ", "").replace("...", "")
            tools_called.append(tool_name)
        elif '"token"' in chunk:
            data = json.loads(chunk.replace("data: ", ""))
            final_response.append(data.get("token", ""))

    return {
        "tool_called": len(tools_called) > 0,
        "tool_name": tools_called[0] if tools_called else None,
        "response": "".join(final_response),
    }


def check_tool_usage(run, example):
    expected = example.outputs
    actual = run.outputs

    if "tool_called" not in actual:
        return {
            "key": "tool_call_correct",
            "score": 0,
            "comment": "Target failed - tool schema error",
        }

    if actual["tool_called"] != expected["tool_called"]:
        return {
            "key": "tool_call_correct",
            "score": 0,
            "comment": f"Expected tool_called={expected['tool_called']}, got {actual['tool_called']}",
        }
    if expected["tool_called"] and actual["tool_name"] != expected["tool_name"]:
        return {
            "key": "tool_call_correct",
            "score": 0,
            "comment": f"Wrong tool: expected {expected['tool_name']}, got {actual['tool_name']}",
        }

    return {"key": "tool_call_correct", "score": 1, "comment": "Correct"}


async def main():
    global service

    conninfo = (
        f"postgresql://{env_config.postgres_user}:"
        f"{env_config.postgres_password}@localhost:5432/"
        f"{env_config.postgres_db}?sslmode=disable"
    )

    async with AsyncConnectionPool(
        conninfo=conninfo,
        max_size=5,
        kwargs={"autocommit": True, "prepare_threshold": None},
    ) as pool:
        checkpointer = BotMemory(pool)
        await checkpointer.setup()

        llm = get_strategy(LLMProviders.GROQ).create_model()
        service = AgentBotService(llm=llm, checkpointer=checkpointer)

        await aevaluate(
            target,
            data="ragbot-test-tools",
            evaluators=[check_tool_usage],
            experiment_prefix="tool-call-eval",
        )


if __name__ == "__main__":
    asyncio.run(main())
