from datetime import datetime
from src.models.news import DeepAnalysis, TradingSignal
from src.services.llm_service import LLMService
from src.config import settings

class DecisionEngine:
    def __init__(self, llm: LLMService):
        self.llm = llm
    
    async def generate_signal(self, analysis: DeepAnalysis) -> TradingSignal:
        prompt = f"""
        Convert this analysis to trading signal:
        {analysis.model_dump_json()}
        
        Business rules:
        - Confidence > 0.8 → actionable signal
        - |sentiment| > 0.9 → HIGH urgency
        - Position size: confidence * 0.1 (max 10% portfolio)
        - Risk limit: always 2%
        
        Return ONLY valid TradingSignal JSON:
        {{
            "ticker": "{analysis.ticker}",
            "signal_type": "BUY|SELL|HOLD|ALERT",
            "confidence": 0.92,
            "urgency": "HIGH|MEDIUM|LOW",
            "position_size": 0.05,
            "risk_limit": 0.02,
            "reasoning": "detailed reasoning...",
            "timestamp": "{datetime.utcnow().isoformat()}"
        }}
        """
        
        signal_json = await self.llm.generate(prompt)
        return TradingSignal.parse_raw(signal_json)
