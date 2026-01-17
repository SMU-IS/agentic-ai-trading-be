import json

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph

from app.schemas.state import AgentState


class TradingWorkflow:
    def __init__(self, llm_client, broker_client):
        self.llm = llm_client
        self.broker = broker_client
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)

        # 1. Nodes
        # graph.add_node("lookup_context", self.node_lookup_qdrant)
        graph.add_node("reasoning", self.node_decide_trade)
        graph.add_node("execute", self.node_execute_trade)

        # 2. Edges
        # workflow.add_edge(START, "lookup_context")
        # workflow.add_edge("lookup_context", "reasoning") # TODO: use this once its completed
        graph.add_edge(START, "reasoning")

        # Conditional: Only trade if the brain says so
        graph.add_conditional_edges(
            "reasoning", self.edge_should_execute, {True: "execute", False: END}
        )

        graph.add_edge("execute", END)

        return graph.compile()

    """
    Nodes Logic
    - node_lookup_qdrant
    - node_reasoning
    - node_execute_trade
    """

    async def node_lookup_qdrant(self, state: AgentState):
        """
        Memory: Fetches historical context or news related to the ticker.
        """
        print(
            f"   [🔍 Qdrant] Searching for historical context on {state['ticker']}..."
        )

    # TODO: Add in qdrant retrieval logic

    async def node_decide_trade(self, state: AgentState):
        """
        Brain: Uses Ollama to decide on the trade.
        """

        print(
            f"   [🧠 LLM Brain] Analyzing {state['ticker']} for {state['user_id']}..."
        )

        # 1. Prompt
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a Portfolio Manager.
                Analyse the following market signal and portfolio status.

                DECISION RULES:
                - BUY if sentiment is bullish (score > 0.7) and risk is aggressive.
                - SELL if sentiment is bearish (score < 0.3) and we own the stock.
                - HOLD otherwise.

                Return ONLY a JSON object in this format:
                {{ "action": "BUY", "qty": 5, "reason": "Sentiment is strong" }}
                """,
                ),
                (
                    "human",
                    """
                Ticker: {ticker}
                Signal: {signal}
                Portfolio: {portfolio}
                Risk Profile: {risk_profile}
                """,
                ),
            ]
        )

        # 2. Invoke Ollama
        chain = prompt | self.llm
        response = await chain.ainvoke(
            {
                "ticker": state["ticker"],
                "signal": state["signal"],
                "portfolio": state["portfolio"],
                "risk_profile": state["risk_profile"],
            }
        )

        # 3. Parse JSON Output
        try:
            content = response.content.strip()

            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            decision = json.loads(content)

        except json.JSONDecodeError:
            print(f"❌ Failed to parse JSON from LLM: {response.content}")
            decision = {"action": "HOLD", "qty": 0, "reason": "JSON Parse Error"}

        return {
            "action": decision.get("action", "HOLD"),
            "order_details": {"ticker": state["ticker"], "qty": decision.get("qty", 0)},
            "should_execute": decision.get("action") in ["BUY", "SELL"],
            "reasoning": decision.get("reason", "No reason provided"),
        }

    async def node_execute_trade(self, state: AgentState):
        """
        Hands.
        To execute via Broker API.
        """

        print(
            f"!!! [🤝🏻 Market Access] Executing {state['action']} {state['order_details']}"
        )

        # TODO: Invoke brokerage API service

        return {}

    # ###### Edge Logic ######
    def edge_should_execute(self, state: AgentState):
        return state["should_execute"]

    # ###### Public Runner ######
    async def run(self, input_data: dict):
        result = await self.graph.ainvoke(input_data)  # type: ignore

        return result
