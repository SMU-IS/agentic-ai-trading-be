from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from src.services.redis_service import RedisService
from src.agents import NewsParser, ThresholdMonitor, DeepAnalyzer, DecisionEngine

class AgentState(TypedDict):
    articles: list
    topics: list
    triggered_topics: list
    analyses: list
    signals: list

async def parse_news(state: AgentState):
    parser = NewsParser(llm_service)
    all_topics = []
    for article in state["articles"]:
        topics = await parser.extract_tickers_topics(article)
        all_topics.extend(topics)
    return {"topics": all_topics}

async def monitor_thresholds(state: AgentState):
    monitor = ThresholdMonitor(redis_service)
    triggered = await monitor.check_triggers(state["topics"])
    return {"triggered_topics": [t.model_dump() for t in triggered]}

async def deep_analyze(state: AgentState):
    analyzer = DeepAnalyzer(llm_service)
    analyses = []
    for topic_data in state["triggered_topics"]:
        topic = TickerTopic(**topic_data)
        analysis = await analyzer.analyze(topic)
        analyses.append(analysis)
    return {"analyses": [a.model_dump() for a in analyses]}

async def generate_signals(state: AgentState):
    engine = DecisionEngine(llm_service)
    signals = []
    for analysis_data in state["analyses"]:
        analysis = DeepAnalysis(**analysis_data)
        signal = await engine.generate_signal(analysis)
        signals.append(signal)
        await redis_service.publish_signal(signal.model_dump())
    return {"signals": [s.model_dump() for s in signals]}

# Build workflow
workflow = StateGraph(AgentState)
workflow.add_node("parse", parse_news)
workflow.add_node("monitor", monitor_thresholds)
workflow.add_node("analyze", deep_analyze)
workflow.add_node("signals", generate_signals)

workflow.set_entry_point("parse")
workflow.add_edge("parse", "monitor")
workflow.add_edge("monitor", "analyze")
workflow.add_edge("analyze", "signals")
workflow.add_edge("signals", END)

app = workflow.compile()
