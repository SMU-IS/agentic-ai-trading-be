from typing import List
from src.models.news import TickerTopic, DeepAnalysis, ResearchQuestion
from src.services.llm_service import LLMService

class DeepAnalyzer:
    def __init__(self, llm: LLMService):
        self.llm = llm
    
    async def analyze(self, topic: TickerTopic) -> DeepAnalysis:
        # Generate research questions
        questions_prompt = f"""
        For ticker {topic.ticker} topic '{topic.topic.replace('_', ' ')}' with sentiment {topic.sentiment},
        generate 3 specific research questions to verify this signal.
        Focus on confirmation, credibility, and impact magnitude.
        
        Return JSON list: [{{"question": "Is AAPL supply chain disruption confirmed?", "sources_needed": ["company_filings", "supplier_news"]}}]
        """
        
        questions = await self.llm.generate_list(questions_prompt)
        
        # Mock web search verification (replace with real search)
        verification_prompt = f"""
        Verify: {topic.ticker} {topic.topic.replace('_', ' ')}
        Sentiment: {topic.sentiment}
        Questions: {questions}
        
        Analyze credibility across sources. Return JSON:
        {{
            "verified": true,
            "confidence": 0.92,
            "summary": "Confirmed by 3 sources...",
            "research_questions": [...]
        }}
        """
        
        analysis_json = await self.llm.generate(verification_prompt)
        return DeepAnalysis.parse_raw(analysis_json)
