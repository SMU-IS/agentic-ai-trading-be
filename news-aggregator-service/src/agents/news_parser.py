from typing import List
from src.models.news import NewsArticle, TickerTopic
from src.services.llm_service import LLMService

class NewsParser:
    def __init__(self, llm: LLMService):
        self.llm = llm
    
    async def extract_tickers_topics(self, article: NewsArticle) -> List[TickerTopic]:
        prompt = f"""
        Analyze this news article and extract:
        1. Stock tickers mentioned (AAPL, TSLA, etc.)
        2. Main market topics/themes (supply chain, Fed rates, earnings, etc.)
        
        Article: {article.title + ' ' + article.content[:2000]}
        
        Return JSON: [{{"ticker": "AAPL", "topic": "supply_chain", "sentiment": 0.7}}]
        """
        
        response = await self.llm.generate(prompt)
        topics = self.llm.parse_json_list(response)
        
        return [
            TickerTopic(
                ticker=t["ticker"].upper(),
                topic=t["topic"].lower().replace(" ", "_"),
                sentiment=t.get("sentiment", article.sentiment)
            ) 
            for t in topics
        ]
