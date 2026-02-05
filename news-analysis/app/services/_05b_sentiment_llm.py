"""
LLM-Based Sentiment Analysis Service
File: news-analysis/app/services/_05b_sentiment_llm.py

Uses Ollama LLM for sentiment analysis with detailed reasoning.
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional
from dataclasses import dataclass

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Import config
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import env_config

logger = logging.getLogger(__name__)


@dataclass
class LLMSentimentResult:
    """Structured LLM sentiment analysis result"""
    sentiment_label: str
    sentiment_score: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    reasoning: str
    key_factors: List[str]
    raw_response: Optional[Dict] = None


class LLMSentimentService:
    """
    Sentiment analysis using Ollama LLM.

    Uses Ollama LLM for nuanced financial sentiment analysis with detailed reasoning.
    Better at understanding context, sarcasm, and complex financial language.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        model_name: str = env_config.large_language_model or "llama3:8b",
        model_provider: str = "ollama",
        temperature: float = 0.1
    ):
        if self._initialized:
            return

        logger.info("Initializing LLM Sentiment Service...")

        self.model_name = model_name
        self.model_provider = model_provider

        try:
            self.llm: BaseChatModel = init_chat_model(
                model=model_name,
                model_provider=model_provider,
                temperature=temperature,
            )
            self.parser = JsonOutputParser()
            logger.info(f"LLM initialized: {model_provider}/{model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            self.llm = None
            self.parser = None

        # Define the sentiment analysis prompt
        self.sentiment_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                """You are a financial sentiment analyst specializing in social media and news content.
Your task is to analyze the sentiment of financial posts/news and provide structured output.

Consider these factors:
1. Overall tone (bullish, bearish, neutral)
2. Financial slang (moon, rocket, tendies = bullish; rekt, dump, rug = bearish)
3. Emojis sentiment (🚀📈💎 = bullish; 📉💀🤡 = bearish)
4. Factual vs speculative language
5. Sarcasm and irony (common on Reddit)
6. Event impact (earnings, M&A, regulatory)

Output ONLY valid JSON with no additional text or explanation."""
            ),
            (
                "user",
                """Analyze the sentiment of this financial content:

Text: {text}

Return ONLY a JSON object with this exact structure:
{{
    "sentiment_label": "positive" or "negative" or "neutral",
    "sentiment_score": <float from -1.0 (very bearish) to 1.0 (very bullish)>,
    "confidence": <float from 0.0 to 1.0>,
    "reasoning": "<1-2 sentence explanation of why this sentiment was assigned>",
    "key_factors": ["<factor 1>", "<factor 2>", "<factor 3>"]
}}

Be decisive - avoid neutral unless truly ambiguous. Financial posts usually have clear sentiment."""
            )
        ])

        self._initialized = True
        logger.info("LLM Sentiment Service initialized")

    async def analyze(self, text: str) -> LLMSentimentResult:
        """
        Analyze sentiment using LLM.

        Args:
            text: Text to analyze

        Returns:
            LLMSentimentResult with sentiment analysis
        """
        if not self.llm:
            logger.error("LLM not initialized")
            return self._create_fallback_result("LLM not initialized")

        if not text or not text.strip():
            return self._create_fallback_result("Empty text")

        # Truncate very long text
        max_chars = 2000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        try:
            chain = self.sentiment_prompt | self.llm | self.parser
            result = await chain.ainvoke({"text": text})

            # Validate and extract result
            return self._parse_llm_response(result)

        except Exception as e:
            logger.error(f"LLM sentiment analysis failed: {e}")
            return self._create_fallback_result(f"Analysis error: {str(e)[:100]}")

    def analyze_sync(self, text: str) -> LLMSentimentResult:
        """
        Synchronous wrapper for analyze().
        """
        return asyncio.run(self.analyze(text))

    async def analyze_batch(
        self,
        texts: List[str],
        batch_size: int = 5
    ) -> List[LLMSentimentResult]:
        """
        Analyze multiple texts in batches.

        Args:
            texts: List of texts to analyze
            batch_size: Number of concurrent analyses

        Returns:
            List of LLMSentimentResult
        """
        results = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            # Run batch concurrently
            batch_tasks = [self.analyze(text) for text in batch]
            batch_results = await asyncio.gather(*batch_tasks)
            results.extend(batch_results)

        return results

    async def analyse(self, item: Dict) -> Dict:
        """
        Analyze a single item for sentiment using LLM.
        Returns the item enriched with LLM sentiment scores.
        """
        # Extract text from nested structure
        content = item.get('content', {})
        text = (
            content.get('clean_combined_withurl', '') or
            content.get('clean_combined_withouturl', '') or
            content.get('clean_combined', '') or
            item.get('clean_combined', '') or
            item.get('clean_title', '') or
            ''
        )

        result = await self.analyze(text)

        # Enrich item with LLM sentiment data
        item['llm_sentiment_score'] = result.sentiment_score
        item['llm_sentiment_label'] = result.sentiment_label
        item['llm_sentiment_confidence'] = result.confidence
        item['llm_sentiment_reasoning'] = result.reasoning
        item['llm_sentiment_factors'] = result.key_factors

        return item

    def _parse_llm_response(self, response: Dict) -> LLMSentimentResult:
        """
        Parse and validate LLM response.
        """
        # Extract fields with defaults
        sentiment_label = response.get('sentiment_label', 'neutral').lower()
        if sentiment_label not in ['positive', 'negative', 'neutral']:
            sentiment_label = 'neutral'

        sentiment_score = response.get('sentiment_score', 0.0)
        # Clamp to [-1, 1]
        sentiment_score = max(-1.0, min(1.0, float(sentiment_score)))

        confidence = response.get('confidence', 0.5)
        # Clamp to [0, 1]
        confidence = max(0.0, min(1.0, float(confidence)))

        reasoning = response.get('reasoning', 'No reasoning provided')

        key_factors = response.get('key_factors', [])
        if not isinstance(key_factors, list):
            key_factors = [str(key_factors)]

        return LLMSentimentResult(
            sentiment_label=sentiment_label,
            sentiment_score=round(sentiment_score, 6),
            confidence=round(confidence, 6),
            reasoning=reasoning,
            key_factors=key_factors,
            raw_response=response
        )

    def _create_fallback_result(self, reason: str) -> LLMSentimentResult:
        """
        Create a neutral fallback result when analysis fails.
        """
        return LLMSentimentResult(
            sentiment_label="neutral",
            sentiment_score=0.0,
            confidence=0.0,
            reasoning=reason,
            key_factors=["analysis_failed"],
            raw_response=None
        )


# Singleton instance
llm_sentiment_service = LLMSentimentService()


# Main for testing
async def main():
    print("="*80)
    print("LLM SENTIMENT SERVICE TEST")
    print("="*80)

    test_texts = [
        "AAPL just crushed earnings! Revenue up 15% YoY. 🚀🚀🚀 To the moon!",
        "This stock is going to dump hard. Management is incompetent. Sell everything.",
        "Apple Inc reported Q4 earnings of $1.50 per share, meeting analyst expectations.",
        "Diamond hands! 💎🙌 HODL through the dip, tendies coming soon!",
        "Complete rugpull incoming, devs are exit scamming. RIP my portfolio 💀",
    ]

    service = LLMSentimentService()

    print("\nAnalyzing test texts...\n")

    for i, text in enumerate(test_texts, 1):
        print(f"Test {i}: {text[:60]}...")
        result = await service.analyze(text)
        print(f"  Label: {result.sentiment_label}")
        print(f"  Score: {result.sentiment_score}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Reasoning: {result.reasoning}")
        print(f"  Factors: {result.key_factors}")
        print("-"*80)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
