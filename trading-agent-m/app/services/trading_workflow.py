import json

from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, START, StateGraph
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import FieldCondition, Filter, MatchValue

from app.core.qdrant import QdrantManager
from app.schemas.state import AgentState


class TradingWorkflow:
    def __init__(self, llm_client, broker_client):
        self.llm = llm_client
        self.broker = broker_client
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)

        # 1. Nodes
        graph.add_node("lookup_context", self.node_lookup_qdrant)
        graph.add_node("reasoning", self.node_decide_trade)
        graph.add_node("execute", self.node_execute_trade)

        # 2. Edges
        graph.add_edge(START, "lookup_context")
        graph.add_edge(
            "lookup_context", "reasoning"
        )  # TODO: use this once its completed
        # graph.add_edge(START, "reasoning")

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

        qdrant_client = QdrantManager.get_client()
        try:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="ticker", match=MatchValue(value=state["ticker"])
                    )
                ]
            )

            if "query_vector" not in state:
                import numpy as np

                state["query_vector"] = np.random.rand(10).tolist()
                print("   [🔍 Qdrant] Generated dummy query vector.")

            search_results = await qdrant_client.query_points(
                collection_name="historical_data",
                query=state["query_vector"],
                query_filter=query_filter,
                limit=5,
            )

            results = search_results.points

            state["historical_context"] = [
                {
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload,
                }
                for result in results
            ]
            print(
                f"   [✅ Qdrant] Retrieved {len(results)} results for {state['ticker']}."
            )

        except (UnexpectedResponse, Exception) as e:
            print(f"   [❌ Qdrant Error] Could not connect or query failed: {e}")

            state["historical_context"] = []

        finally:
            await qdrant_client.close()

        return state

    # async def node_decide_trade(self, state: AgentState):
    #     """
    #     Brain: Uses Ollama to decide on the trade.
    #     """

    #     print(
    #         f"   [🧠 LLM Brain] Analyzing {state['ticker']} for {state['user_id']}..."
    #     )

    #     # 1. Prompt
    #     prompt = ChatPromptTemplate.from_messages(
    #         [
    #             (
    #                 "system",
    #                 """You are a Portfolio Manager.
    #             Analyse the following market signal and portfolio status.

    #             DECISION RULES:
    #             - BUY if sentiment is bullish (score > 0.7) and risk is aggressive.
    #             - SELL if sentiment is bearish (score < 0.3) and we own the stock.
    #             - HOLD otherwise.

    #             Return ONLY a JSON object in this format:
    #             {{ "action": "BUY", "qty": 5, "reason": "Sentiment is strong" }}
    #             """,
    #             ),
    #             (
    #                 "human",
    #                 """
    #             Ticker: {ticker}
    #             Signal: {signal}
    #             Portfolio: {portfolio}
    #             Risk Profile: {risk_profile}
    #             """,
    #             ),
    #         ]
    #     )

    #     # 2. Invoke Ollama
    #     chain = prompt | self.llm
    #     response = await chain.ainvoke(
    #         {
    #             "ticker": state["ticker"],
    #             "signal": state["signal"],
    #             "portfolio": state["portfolio"],
    #             "risk_profile": state["risk_profile"],
    #         }
    #     )

    #     # 3. Parse JSON Output
    #     try:
    #         content = response.content.strip()

    #         if "```json" in content:
    #             content = content.split("```json")[1].split("```")[0].strip()
    #         elif "```" in content:
    #             content = content.split("```")[1].split("```")[0].strip()

    #         decision = json.loads(content)

    #     except json.JSONDecodeError:
    #         print(f"❌ Failed to parse JSON from LLM: {response.content}")
    #         decision = {"action": "HOLD", "qty": 0, "reason": "JSON Parse Error"}

    #     return {
    #         "action": decision.get("action", "HOLD"),
    #         "order_details": {"ticker": state["ticker"], "qty": decision.get("qty", 0)},
    #         "should_execute": decision.get("action") in ["BUY", "SELL"],
    #         "reasoning": decision.get("reason", "No reason provided"),
    #     }

    async def node_decide_trade(self, state: AgentState):
        """
        Brain: Uses LLM for short-term swing trades driven by news volatility.
        Goal: Capture 2-5 day swings against short-term news-driven volatility.
        """
        print(
            f"   [🧠 Swing Trading Brain] Analyzing {state['ticker']} for {state['user_id']}..."
        )

        # Enhanced prompt for news-driven swing trading
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are an expert short-term swing trader (2-5 day horizon) specializing in news-driven volatility.

                STRATEGY: Capture short-term swings from news sentiment shocks. Trade against overreactions.

                CRITERIA FOR SWING TRADES:
                1. NEWS IMPACT: Strong sentiment shift (>0.4 absolute score) OR high-impact event (earnings, downgrade, etc.)
                2. TECHNICAL CONFIRMATION:
                - BUY: Price near support, RSI < 40 (oversold), bullish divergence
                - SELL: Price near resistance, RSI > 70 (overbought), bearish divergence
                3. VOLATILITY: ATR > 20-day average (swing opportunity exists)
                4. REGIME: Avoid if VIX > 25 (too chaotic for swings)

                POSITION SIZING & RISK:
                - Entry: Market or pullback to key level
                - SL: 1.5x ATR from entry (volatility-adjusted)
                - TP: 2.5x ATR from entry (2:1 R:R minimum)
                - Max risk: 1% account per trade

                EXISTING POSITIONS:
                - If you own it and news turns against: Scale out 50-100%
                - Never add to losers

                IGNORE if:
                - Weak news (<0.3 sentiment score)
                - No technical confirmation
                - Poor R:R (< 1.5:1)

                Return ONLY valid JSON. Never return invalid trades.
                """,
                ),
                (
                    "human",
                    """
                CURRENT MARKET SNAPSHOT:
                Ticker: {ticker}
                Current Price: {current_price}
                ATR (14): {atr}

                NEWS SIGNAL:
                Sentiment: {sentiment} (score: {score})
                Event Type: {event_type}
                Historical Context: {historical_context}

                PORTFOLIO:
                {portfolio}

                RISK PROFILE: {risk_profile}

                ANALYSIS REQUIRED:
                1. News impact assessment
                2. Technical setup (support/resistance, RSI, momentum)
                3. Volatility regime (swing viable?)
                4. Entry/SL/TP calculation (ATR-based)
                5. Position sizing
                6. Clear thesis (why this swing works)

                Return JSON:
                {{
                "action": "BUY" | "SELL" | "HOLD",
                "confidence": 0.0-1.0,
                "entry_price": float,
                "stop_loss": float,
                "take_profit": float,
                "qty": float,
                "risk_reward": "X:1",
                "thesis": "Detailed reasoning with news + technical justification"
                }}
                """,
                ),
            ]
        )

        # 2. Prepare enriched input for LLM
        input_vars = {
            "ticker": state["ticker"],
            "current_price": state["signal"].get("current_price", 150.0),  # fallback
            "atr": state["signal"].get("atr", 3.0),  # fallback 14-period ATR
            "sentiment": state["signal"].get("sentiment", "neutral"),
            "score": state["signal"].get("score", 0.0),
            "event_type": state["signal"].get("event_type", "general"),
            "historical_context": state.get("historical_context", []),
            "portfolio": state["portfolio"],
            "risk_profile": state["risk_profile"],
        }

        # 3. Invoke LLM
        chain = prompt | self.llm
        response = await chain.ainvoke(input_vars)

        # 4. Parse enhanced JSON
        try:
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json").split("```").strip()[1]
            elif "```" in content:
                content = content.split("```")[28].split("```")[0].strip()

            decision = json.loads(content)

            # Validate required fields
            if decision.get("action") not in ["BUY", "SELL", "HOLD"]:
                decision["action"] = "HOLD"

        except json.JSONDecodeError:
            print(f"❌ LLM JSON parse failed: {response.content[:200]}...")
            decision = {
                "action": "HOLD",
                "confidence": 0.0,
                "entry_price": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "qty": 0.0,
                "risk_reward": "0:1",
                "thesis": "JSON parsing error - no trade",
            }

        # 5. Return structured state update
        return {
            "action": decision.get("action", "HOLD"),
            "order_details": {
                "ticker": state["ticker"],
                "side": decision.get("action", "HOLD"),
                "qty": float(decision.get("qty", 0)),
                "entry_price": float(decision.get("entry_price", 0)),
                "stop_loss": float(decision.get("stop_loss", 0)),
                "take_profit": float(decision.get("take_profit", 0)),
            },
            "should_execute": decision.get("action") in ["BUY", "SELL"]
            and decision.get("confidence", 0) > 0.6,
            "reasoning": decision.get("thesis", "No reasoning provided"),
            "confidence": decision.get("confidence", 0.0),
            "risk_reward": decision.get("risk_reward", "0:1"),
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
        return state.get("should_execute", False)

    # ###### Public Runner ######
    async def run(self, input_data: dict):
        result = await self.graph.ainvoke(input_data)  # type: ignore

        return result
