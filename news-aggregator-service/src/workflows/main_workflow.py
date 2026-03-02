# src/workflows/main_workflow.py
from typing import TypedDict
from langgraph.graph import StateGraph, END
from src.services.redis_service import RedisService
from src.services.llm_service import LLMService
from src.services.database import post_deepanalysis
from src.agents import ThresholdMonitor, DeepAnalyzer, lookup_qdrant
from src.models.state import DeepAnalysis, TickerSentiment
import os

class AgentState(TypedDict):
    articles: list
    topics: list
    triggered_topics: list
    deep_analysis: DeepAnalysis  # Now contains complete trading decisions!
    qdrant_context: list[dict]
    signal_id: str
    signal_payload: dict


# Initialize services & build workflow
class WorkflowManager:
    def __init__(self):
        self.redis_service = None
        self.llm_service = None
        self.app = None

    async def initialize(self, redis_service: RedisService):
        """Initialize services and compile workflow"""
        self.redis_service = redis_service
        self.llm_service = LLMService()
        
        # Build workflow
        self.app = self._build_workflow()
        print("✅ TradingWorkflow initialized!")
        return self
    
    def _build_workflow(self):
        """Build LangGraph workflow"""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("parse", self.parse_news)
        workflow.add_node("monitor", self.monitor_thresholds)
        workflow.add_node("qdrant_lookup", self.get_qdrant_vector)
        workflow.add_node("analyze", self.deep_analyze)
        workflow.add_node("gensignals", self.generate_signals)
        
        # Edges
        workflow.set_entry_point("parse")
        workflow.add_edge("parse", "monitor")
        # workflow.add_edge("qdrant_lookup", "analyze")

        # Conditional edges
        workflow.add_conditional_edges(
            "qdrant_lookup",
            self.has_qdrant_points,
            {True: "analyze", False: END}
        )
        workflow.add_conditional_edges(
            "monitor", 
            self.has_triggered_topics,
            {True: "qdrant_lookup", False: END}
        )
        workflow.add_conditional_edges(
            "analyze", 
            self.has_trade_signal,
            {True: "gensignals", False: END}
        )
        workflow.add_edge("gensignals", END)
        
        return workflow.compile()
    
    async def run(self, input_data: dict) -> dict:
        """Run the compiled workflow"""
        if self.app is None:
            await self.initialize()
        return await self.app.ainvoke(input_data)
    
    def has_triggered_topics(self, state: AgentState) -> str:
        """Router: triggered topics? → qdrant_lookup : END"""
        triggered_len = len(state.get("triggered_topics", []))
        print(f"🔀 Router: {triggered_len} triggered topics")
        return  triggered_len > 0
        
    def has_trade_signal(self, state: AgentState) -> str:
        """Router: has trade signal? → gensignals : END"""
        deep_analysis = state.get("deep_analysis", None)
        if deep_analysis and deep_analysis.trade_signal != "NO_TRADE":
            print(f"🔀 Router: Found trade signal for {deep_analysis.ticker}")
            return True
        print("🔀 Router: No actionable trade signal found")
        return False
    
    def has_qdrant_points(self, state: AgentState) -> str:
        """Skip analysis if no qdrant data found on topic"""
        qdrant_points = len(state.get("qdrant_context", []))
        print(f"🔀 Has Qdrant Points: {qdrant_points > 0} ({qdrant_points})")
        return  qdrant_points > 0
    
    async def export_graph(self):
        """Simple PNG export - just get the PNG file"""
        if not self.app:
            print("❌ Initialize workflow first")
            return
        
        folder_name = "public"
        os.makedirs(folder_name, exist_ok=True)
        
        filepath = os.path.join(folder_name, "news-aggregator-flow.png")
        
        try:
            self.app.get_graph().draw_mermaid_png()
            png_bytes = self.app.get_graph().draw_mermaid_png()
            
            with open(filepath, "wb") as f:
                f.write(png_bytes)
                
            print(f"✅ PNG saved: {os.path.abspath(filepath)}")
            
        except Exception as e:
            print(f"❌ PNG failed: {e}")

    # Agent Nodes
    # ###### Node Logic ######
    async def parse_news(self, state: AgentState) -> AgentState:
        """Extract tickers/topics from articles"""
        print("🗞️ Parsing news articles for tickers/topics")
        
        all_articles = []
        for article in state["articles"]:
            print(article)
            # Convert dict back to model if needed
            if isinstance(article, dict):
                article = TickerSentiment(**article)    
                all_articles.append(article)
                print(f"\n📰 Parsing article for tickers/topics: {article.ticker}")
        state["articles"] = all_articles
        return state

    async def monitor_thresholds(self, state: AgentState) -> AgentState:
        """Check sentiment/volume triggers"""
        print("🚦 Monitoring thresholds for topics")
        # print(state["articles"])

        monitor = ThresholdMonitor(self.redis_service)
        triggered = await monitor.check_triggers(state["articles"])
        for sentiment in triggered:
            print(f"🎯 TRIGGERED: {sentiment.ticker} {sentiment.event_type} "
                f"(score: {sentiment.sentiment_score:.2f}, vol: {getattr(sentiment, 'volume', 0)})")
            state["triggered_topics"].append({
                "ticker": sentiment.ticker,
                "event_type": sentiment.event_type,
            })
        return state 

    async def get_qdrant_vector(self,state: AgentState) -> AgentState:
        print("================================")
        print("🔍 Looking up Qdrant for historical context")
        articles = state.get("articles", [])
        if not articles:
            state["qdrant_context"] = []
            return state
        
        article = articles[0]
        ticker = getattr(article, "ticker", None)
        event_type = getattr(article, "event_type", None)
        
        if not ticker or not event_type:
            state["qdrant_context"] = []
            return state
        
        qdrant_content = await lookup_qdrant(ticker, event_type)
        # print("QDRANT CONTENT:", qdrant_content)
        state["qdrant_context"] = qdrant_content
        print("🔍 Qdrant content points retrieved:", len(qdrant_content))
        return state

    async def deep_analyze(self, state: AgentState) -> AgentState:
        """Deep analysis → Complete trading decisions"""
        print("🔬 Deep analysis of triggered topics")
        analyzer = DeepAnalyzer(self.llm_service)
        # print(state.keys())
        news_content_compile = [a.get("text_content", "") for a in state["qdrant_context"]]
        news_content = "\n".join(news_content_compile)
        article = state["articles"][0]
        print(f"Analyzing article: {article.ticker} {article.event_type}")
        analysis = await analyzer.analyze(news_content, article)
        analyzer.print_analysis(analysis)
        state["deep_analysis"] = analysis
    
        # Post the analysis
        response = post_deepanalysis(analysis)

        # Safe ID extraction with validation
        if response and isinstance(response, dict):
            if response.get("success") and "id" in response:
                signal_id = response["id"]
                print(f"🎯 Signal stored with ID: {signal_id}")
                # Use the ID for next steps
                state["signal_id"] = signal_id
                
                # Send news analysis to News notification stream
                await self.redis_service.publish_news(signal_id)
                print(f"📡 News published to Redis: {signal_id}")
            else:
                print(f"❌ API error: {response}")
                signal_id = None
        else:
            print("❌ No response from API")
            signal_id = None
        return state

    async def generate_signals(self, state: AgentState) -> AgentState:
        """Convert analyses → Trading signals → Redis"""
        print("⚠️ Signal generation")
        signal_id = state.get("signal_id")
        # Publish to Redis for real-time consumers
        if signal_id:
            await self.redis_service.publish_signal(signal_id)
            print(f"📡 Signal published to Redis: {signal_id}")
        return state

# Global app instance
async def setup_workflow(redis_service: RedisService):
    workflow = WorkflowManager()
    await workflow.initialize(redis_service)
    return workflow