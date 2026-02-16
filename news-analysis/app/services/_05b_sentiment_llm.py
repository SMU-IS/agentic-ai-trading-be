"""
LLM-Based Sentiment Analysis Service
File: news-analysis/app/services/_05b_sentiment_llm.py

Uses Groq LLM (Llama 3.3 70B Versatile) for per-ticker sentiment analysis with detailed reasoning.
Analyzes sentiment for each ticker mentioned in financial news/social media posts.
Supports sarcasm detection, financial slang (Reddit/WSB), and emoji interpretation.
Uses few-shot prompting from _05_sentiment_prompts.py.
"""

import asyncio
import json
import logging
from typing import Dict, Optional
from dataclasses import dataclass

from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Import config
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import env_config

# Import few-shot prompts (relative import to avoid circular import via __init__.py)
from ._05_sentiment_prompts import build_sentiment_prompt

logger = logging.getLogger(__name__)


@dataclass
class TickerSentiment:
    """Sentiment analysis result for a single ticker"""
    ticker: str
    official_name: str
    sentiment_score: float  # -1.0 to 1.0
    sentiment_label: str  # positive, negative, neutral
    reasoning: str


@dataclass
class LLMSentimentResult:
    """Complete sentiment analysis result for a news item (per-ticker only)"""
    ticker_sentiments: Dict[str, Dict]  # Per-ticker sentiment data
    analysis_successful: bool = True
    error_message: Optional[str] = None


class LLMSentimentService:
    """
    Per-ticker sentiment analysis using Groq LLM (Llama 3.3 70B) with few-shot prompting.

    Analyzes financial news/social media content (especially Reddit) and generates
    sentiment scores for each ticker mentioned. Designed to handle sarcasm,
    financial slang, and emojis common in Reddit/WSB posts.

    Uses clean_combined_withurl and ticker_metadata from upstream pipeline.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        model_name: str = env_config.large_language_model_llama or "llama-3.3-70b-versatile",
        temperature: float = 0.1
    ):
        if self._initialized:
            return

        logger.info("Initializing LLM Sentiment Service...")

        self.model_name = model_name

        try:
            self.llm = ChatGroq(
                model=model_name,
                api_key=env_config.groq_api_key,
                temperature=temperature,
            )
            self.parser = JsonOutputParser()
            logger.info(f"Groq LLM initialized: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Groq LLM: {e}")
            self.llm = None
            self.parser = None

        self._initialized = True
        logger.info("LLM Sentiment Service initialized")

    async def analyse(self, item: Dict) -> Dict:
        """
        Analyze sentiment for each ticker in the news item.

        Uses clean_combined_withurl as the text input and ticker_metadata
        from upstream ticker identification for per-ticker analysis.

        Args:
            item: Pipeline data with 'content' and 'ticker_metadata'

        Returns:
            Item enriched with per-ticker sentiment scores
        """
        # Extract text from nested structure
        content = item.get('content', {})
        text = content.get('clean_combined_withurl', '')

        # Get ticker metadata from upstream ticker identification
        ticker_metadata = item.get('ticker_metadata', {})

        if not ticker_metadata:
            logger.warning("No ticker_metadata found in item")
            item['sentiment_analysis'] = {
                'error': 'No tickers identified',
                'ticker_sentiments': {}
            }
            return item

        if not text or not text.strip():
            logger.warning("Empty text content")
            item['sentiment_analysis'] = {
                'error': 'Empty content',
                'ticker_sentiments': self._create_fallback_sentiments(ticker_metadata)
            }
            return item

        # Analyze sentiment for all tickers
        result = await self._analyze_tickers(text, ticker_metadata)

        # Enrich ticker_metadata with sentiment data
        for ticker, sentiment_data in result.ticker_sentiments.items():
            if ticker in ticker_metadata:
                ticker_metadata[ticker]['sentiment_score'] = sentiment_data['sentiment_score']
                ticker_metadata[ticker]['sentiment_label'] = sentiment_data['sentiment_label']
                ticker_metadata[ticker]['sentiment_reasoning'] = sentiment_data['reasoning']

        # Update item with enriched data (per-ticker only, no overall)
        item['ticker_metadata'] = ticker_metadata
        item['sentiment_analysis'] = {
            'analysis_successful': result.analysis_successful,
            'ticker_sentiments': result.ticker_sentiments
        }

        if result.error_message:
            item['sentiment_analysis']['error'] = result.error_message

        return item

    async def _analyze_tickers(
        self,
        text: str,
        ticker_metadata: Dict
    ) -> LLMSentimentResult:
        """
        Perform LLM-based sentiment analysis for all tickers using few-shot prompting.

        Args:
            text: The news/post content (clean_combined_withurl)
            ticker_metadata: Dict of ticker -> metadata from ticker identification

        Returns:
            LLMSentimentResult with per-ticker sentiments
        """
        if not self.llm:
            logger.error("LLM not initialized")
            return LLMSentimentResult(
                ticker_sentiments=self._create_fallback_sentiments(ticker_metadata),
                analysis_successful=False,
                error_message="LLM not initialized"
            )

        # Truncate very long text
        max_chars = 3000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."

        # Format ticker info for the prompt
        tickers_info = self._format_tickers_for_prompt(ticker_metadata)

        try:
            # Build few-shot prompt from external prompts file
            prompt_messages = build_sentiment_prompt(text, tickers_info)
            sentiment_prompt = ChatPromptTemplate.from_messages(prompt_messages)

            chain = sentiment_prompt | self.llm | self.parser
            result = await chain.ainvoke({})

            # Parse and validate the response
            ticker_sentiments = self._parse_sentiment_response(result, ticker_metadata, text)

            return LLMSentimentResult(
                ticker_sentiments=ticker_sentiments,
                analysis_successful=True
            )

        except Exception as e:
            logger.error(f"LLM sentiment analysis failed: {e}")
            return LLMSentimentResult(
                ticker_sentiments=self._create_fallback_sentiments(ticker_metadata),
                analysis_successful=False,
                error_message=f"Analysis error: {str(e)[:100]}"
            )

    def _format_tickers_for_prompt(self, ticker_metadata: Dict) -> str:
        """Format ticker metadata for the LLM prompt."""
        lines = []
        for ticker, info in ticker_metadata.items():
            official_name = info.get('OfficialName', ticker)
            event_type = info.get('event_type', 'Unknown')
            lines.append(f"- {ticker} ({official_name}) - Event: {event_type}")
        return "\n".join(lines)

    def _parse_sentiment_response(
        self,
        response: Dict,
        ticker_metadata: Dict,
        text: str = ""
    ) -> Dict[str, Dict]:
        """
        Parse and validate the LLM response.

        Args:
            response: Raw LLM response
            ticker_metadata: Original ticker metadata for validation
            text: Original text for confidence calibration

        Returns:
            Validated per-ticker sentiment dict
        """
        ticker_sentiments = {}
        raw_sentiments = response.get('ticker_sentiments', {})
        num_tickers = len(ticker_metadata)

        for ticker in ticker_metadata.keys():
            if ticker in raw_sentiments:
                raw = raw_sentiments[ticker]

                # Parse and validate sentiment score
                score = float(raw.get('sentiment_score', 0.0))
                score = max(-1.0, min(1.0, score))  # Clamp to [-1, 1]

                # Determine label based on score thresholds
                label = self._score_to_label(score)

                # Get reasoning
                reasoning = raw.get('reasoning', 'No reasoning provided')

                ticker_sentiments[ticker] = {
                    'sentiment_score': round(score, 4),
                    'sentiment_label': label,
                    'reasoning': reasoning,
                    'official_name': ticker_metadata[ticker].get('OfficialName', ticker)
                }
            else:
                # Ticker not in response - use fallback
                ticker_sentiments[ticker] = self._create_fallback_ticker_sentiment(
                    ticker,
                    ticker_metadata[ticker].get('OfficialName', ticker)
                )

        return ticker_sentiments


    def _score_to_label(self, score: float) -> str:
        """
        Convert sentiment score to label.
        Neutral zone: -0.1 to 0.1
        """
        if score > 0.1:
            return "positive"
        elif score < -0.1:
            return "negative"
        else:
            return "neutral"

    def _create_fallback_sentiments(self, ticker_metadata: Dict) -> Dict[str, Dict]:
        """Create fallback neutral sentiments for all tickers."""
        return {
            ticker: self._create_fallback_ticker_sentiment(
                ticker,
                info.get('OfficialName', ticker)
            )
            for ticker, info in ticker_metadata.items()
        }

    def _create_fallback_ticker_sentiment(
        self,
        ticker: str,
        official_name: str
    ) -> Dict:
        """Create a neutral fallback sentiment for a single ticker."""
        return {
            'sentiment_score': 0.0,
            'sentiment_label': 'neutral',
            'reasoning': 'Analysis failed - using neutral fallback',
            'official_name': official_name
        }


# Singleton instance
llm_sentiment_service = LLMSentimentService()


# Main for testing
async def main():
    print("=" * 80)
    print("LLM SENTIMENT SERVICE TEST - Per-Ticker Analysis")
    print("=" * 80)

    # Test case: 3 tickers with Reddit-style content (sarcasm, slang, emojis)
    test_item = {
        'content': {
            'clean_combined_withurl': """
            Apple just crushed earnings! Revenue up 15% YoY, diamond hands on AAPL 🚀🚀🚀
            Meanwhile MSFT cloud growth is slowing down, looks bearish short-term.
            Oh and TSLA? Great job Elon, another recall. Really genius moves 🤡🤡
            Bagholding TSLA at $300 avg, this is absolutely rekt.
            """
        },
        'ticker_metadata': {
            'AAPL': {
                'OfficialName': 'Apple Inc.',
                'event_type': 'EARNINGS_REPORT'
            },
            'MSFT': {
                'OfficialName': 'Microsoft Corporation',
                'event_type': 'EARNINGS_REPORT'
            },
            'TSLA': {
                'OfficialName': 'Tesla Inc.',
                'event_type': 'PRODUCT_RECALL'
            }
        }
    }

    service = LLMSentimentService()

    print("\nAnalyzing test item...\n")
    result = await service.analyse(test_item)

    print("Results:")
    print("-" * 80)

    sentiment_analysis = result.get('sentiment_analysis', {})
    print(f"Analysis Successful: {sentiment_analysis.get('analysis_successful')}")

    print("\nPer-Ticker Sentiments:")
    for ticker, data in sentiment_analysis.get('ticker_sentiments', {}).items():
        print(f"\n  {ticker} ({data.get('official_name')}):")
        print(f"    Score: {data.get('sentiment_score')}")
        print(f"    Label: {data.get('sentiment_label')}")
        print(f"    Reasoning: {data.get('reasoning')}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
