# src/workflows/main_workflow.py
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from src.services.redis_service import RedisService
from src.services.llm_service import LLMService
from src.agents import NewsParser, ThresholdMonitor, DeepAnalyzer
from src.models.news import TickerTopic, DeepAnalysis, TradingSignal, NewsArticle, TickerSentiment

# Global services (initialize once)
redis_service = None
llm_service = None

class AgentState(TypedDict):
    articles: list
    topics: list
    triggered_topics: list
    analyses: list  # Now contains complete trading decisions!
    signals: list

async def parse_news(state: AgentState) -> AgentState:
    """Extract tickers/topics from articles"""
    print("🗞️ Parsing news articles for tickers/topics")
    all_topics = []
    
    for article in state["articles"]:
        # Convert dict back to model if needed
        if isinstance(article, dict):
            article = TickerSentiment(**article)
            print(f"\n📰 Parsing article for tickers/topics: {article.ticker}")
    return {}

async def monitor_thresholds(state: AgentState) -> AgentState:
    """Check sentiment/volume triggers"""
    print("🚦 Monitoring thresholds for topics")
    return {}  # Temporarily disable threshold monitoring
    # monitor = ThresholdMonitor(redis_service)
    # topics = [TickerTopic(**t) for t in state["topics"]]
    # triggered = await monitor.check_triggers(topics)
    
    # print(f"🚨 {len(triggered)}/{len(topics)} topics triggered thresholds")
    # return {"triggered_topics": [t.model_dump() for t in triggered]}

async def deep_analyze(state: AgentState) -> AgentState:
    """Deep analysis → Complete trading decisions"""
    print("🔬 Deep analysis of triggered topics")
    analyzer = DeepAnalyzer(llm_service)
    analyses = []
    
    for topic_data in state["triggered_topics"]:
        topic = TickerTopic(**topic_data)
        print(f"\n🔍 Analyzing {topic.ticker}:{topic.topic}...")
        
        analysis = await analyzer.analyze(topic)
        analyses.append(analysis)
        
        # Pretty print each analysis
        analyzer.print_analysis(analysis)
    
    print(f"✅ Generated {len(analyses)} deep analyses")
    return {"analyses": [a.model_dump() for a in analyses]}

async def generate_signals(state: AgentState) -> AgentState:
    """Convert analyses → Trading signals → Redis"""
    print("⚠️ Signal generation")
    return {}  # Temporarily disable signal generation
    # signals = []
    
    # for analysis_data in state["analyses"]:
    #     analysis = DeepAnalysis(**analysis_data)
        
    #     # Filter actionable signals (confidence >= 7, not NO_TRADE)
    #     if analysis.confidence >= 7 and analysis.trade_signal != "NO_TRADE":
    #         signal = TradingSignal(
    #             ticker=analysis.ticker,
    #             signal_type=analysis.trade_signal,
    #             confidence=analysis.confidence / 10.0,
    #             urgency="HIGH" if analysis.confidence >= 9 else "MEDIUM",
    #             position_size=analysis.position_size_pct / 100,
    #             risk_limit=analysis.stop_loss_pct / 100,
    #             reasoning=f"{analysis.trade_rationale} | {analysis.rumor_summary}",
    #             timestamp=analysis.model_dump().get("timestamp", datetime.utcnow())
    #         )
            
    #         signals.append(signal)
    #         await redis_service.publish_signal(signal.model_dump())
    #         print(f"📡 SENT SIGNAL: {signal.ticker} {signal.signal_type} ({signal.confidence:.2f})")
    
    # print(f"🚀 Published {len(signals)} signals to Redis")
    # return {"signals": [s.model_dump() for s in signals]}

# Initialize services & build workflow
async def initialize_workflow():
    global redis_service, llm_service
    redis_service = RedisService()
    llm_service = LLMService()
    
    await redis_service.connect()
    await llm_service.client.__aenter__()  # httpx client
    
    # Build workflow
    workflow = StateGraph(AgentState)
    workflow.add_node("parse", parse_news)
    workflow.add_node("monitor", monitor_thresholds)
    workflow.add_node("analyze", deep_analyze)
    workflow.add_node("gensignals", generate_signals)
    
    workflow.set_entry_point("parse")
    workflow.add_edge("parse", "monitor")
    workflow.add_edge("monitor", "analyze")
    workflow.add_edge("analyze", "gensignals")
    workflow.add_edge("gensignals", END)
    
    return workflow.compile()

# Global app instance

async def setup_workflow():
    app = await initialize_workflow()
    return app
