"""
LLM-Based Sentiment Analysis Service
File: news-analysis/app/services/_05b_sentiment_llm.py

Uses Gemini LLM for per-ticker sentiment analysis with detailed reasoning.
Analyzes sentiment for each ticker mentioned in financial news/social media posts.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Import config
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import env_config

logger = logging.getLogger(__name__)


@dataclass
class TickerSentiment:
    """Sentiment analysis result for a single ticker"""
    ticker: str
    official_name: str
    sentiment_score: float  # -1.0 to 1.0
    sentiment_label: str  # positive, negative, neutral
    confidence: float  # 0.0 to 1.0
    reasoning: str


@dataclass
class LLMSentimentResult:
    """Complete sentiment analysis result for a news item"""
    ticker_sentiments: Dict[str, Dict]  # Per-ticker sentiment data
    overall_sentiment_score: float  # Weighted average
    overall_sentiment_label: str
    analysis_successful: bool = True
    error_message: Optional[str] = None


class LLMSentimentService:
    """
    Per-ticker sentiment analysis using Gemini LLM.

    Analyzes financial news/social media content and generates sentiment scores
    for each ticker mentioned. Designed to work with the news analysis pipeline
    where ticker_metadata is passed from upstream ticker identification module.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        model_name: str = env_config.large_language_model or "gemini-2.5-flash-lite",
        temperature: float = 0.1
    ):
        if self._initialized:
            return

        logger.info("Initializing LLM Sentiment Service...")

        self.model_name = model_name

        try:
            self.llm = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=env_config.gemini_api_key,
                temperature=temperature,
            )
            self.parser = JsonOutputParser()
            logger.info(f"Gemini LLM initialized: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini LLM: {e}")
            self.llm = None
            self.parser = None

        # Define the per-ticker sentiment analysis prompt
        self.sentiment_prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                """You are an expert financial sentiment analyst specializing in stock market news and social media content analysis.
                    Your task is to analyze the sentiment of financial content FOR EACH SPECIFIC TICKER mentioned. 
                    Different tickers in the same news article may have different sentiments.

                ## Sentiment Score Guidelines
                - Score range: -1.0 (extremely bearish) to +1.0 (extremely bullish)
                - Neutral zone: -0.1 to +0.1 (use only when sentiment is truly ambiguous or factual without opinion)
                - Be decisive: Most financial content has clear directional sentiment

                ## Score Interpretation
                | Score Range | Label | Meaning |
                |-------------|-------|---------|
                | +0.7 to +1.0 | positive | Strongly bullish - major positive catalyst, exceptional news |
                | +0.3 to +0.69 | positive | Moderately bullish - positive developments, optimistic outlook |
                | +0.1 to +0.29 | positive | Slightly bullish - mild positive sentiment, cautious optimism |
                | -0.1 to +0.1 | neutral | Neutral - factual reporting, no clear directional bias |
                | -0.29 to -0.1 | negative | Slightly bearish - mild concerns, cautious pessimism |
                | -0.69 to -0.3 | negative | Moderately bearish - negative developments, pessimistic outlook |
                | -1.0 to -0.7 | negative | Strongly bearish - major negative catalyst, crisis/disaster |

                ## Analysis Factors
                1. **Direct Impact**: How does the news directly affect the company's fundamentals?
                2. **Market Context**: Consider sector trends, competitive dynamics
                3. **Language Tone**: Bullish terms (moon, rocket, buy, undervalued) vs bearish (dump, sell, overvalued, crash)
                4. **Emojis**: 🚀📈💎🔥 = bullish; 📉💀🤡⚠️ = bearish
                5. **Financial Slang**: Reddit/WSB terms (tendies, diamond hands = bullish; bagholding, rekt = bearish)
                6. **Event Type**: Earnings beat/miss, M&A, FDA approval/rejection, legal issues, management changes
                7. **Sarcasm Detection**: Common on Reddit - "great job losing money" is negative despite "great"

                ## Confidence Score Guidelines
                - 0.9-1.0: Very clear sentiment, unambiguous language, single ticker focus
                - 0.7-0.89: Clear sentiment with some nuance or multiple factors
                - 0.5-0.69: Mixed signals, requires interpretation
                - 0.3-0.49: Ambiguous content, low certainty
                - 0.0-0.29: Highly uncertain, conflicting information

                Output ONLY valid JSON. No markdown, no explanations outside JSON."""
            ),
            (
                "user",
                """Analyze the sentiment of this financial content for EACH ticker listed.

                ## News/Post Content
                {text}

                ## Tickers to Analyze
                {tickers_info}

                ## Required Output Format
                Return a JSON object with sentiment analysis for each ticker:

                {{
                    "ticker_sentiments": {{
                        "<TICKER_SYMBOL>": {{
                            "sentiment_score": <float from -1.0 to 1.0>,
                            "sentiment_label": "<positive|negative|neutral>",
                            "confidence": <float from 0.0 to 1.0>,
                            "reasoning": "<1-2 sentence explanation of WHY this sentiment for THIS specific ticker>"
                        }}
                    }}
                }}

                ## Important Rules
                1. Analyze sentiment for EACH ticker separately - they may differ
                2. The reasoning must explain why THIS ticker has THIS sentiment based on the content
                3. Use the full score range - don't cluster around 0
                4. Only use "neutral" (-0.1 to 0.1) when truly ambiguous
                5. Confidence reflects how certain the model is about the sentiment assessment"""
            )
        ])

        self._initialized = True
        logger.info("LLM Sentiment Service initialized")

    async def analyse(self, item: Dict) -> Dict:
        """
        Analyze sentiment for each ticker in the news item.

        Args:
            item: Pipeline data with 'content' and 'ticker_metadata'

        Returns:
            Item enriched with per-ticker sentiment scores
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
                ticker_metadata[ticker]['sentiment_confidence'] = sentiment_data['confidence']
                ticker_metadata[ticker]['sentiment_reasoning'] = sentiment_data['reasoning']

        # Update item with enriched data
        item['ticker_metadata'] = ticker_metadata
        item['sentiment_analysis'] = {
            'overall_sentiment_score': result.overall_sentiment_score,
            'overall_sentiment_label': result.overall_sentiment_label,
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
        Perform LLM-based sentiment analysis for all tickers.

        Args:
            text: The news/post content
            ticker_metadata: Dict of ticker -> metadata from ticker identification

        Returns:
            LLMSentimentResult with per-ticker sentiments
        """
        if not self.llm:
            logger.error("LLM not initialized")
            return LLMSentimentResult(
                ticker_sentiments=self._create_fallback_sentiments(ticker_metadata),
                overall_sentiment_score=0.0,
                overall_sentiment_label="neutral",
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
            chain = self.sentiment_prompt | self.llm | self.parser
            result = await chain.ainvoke({
                "text": text,
                "tickers_info": tickers_info
            })

            # Parse and validate the response (pass text for confidence calibration)
            ticker_sentiments = self._parse_sentiment_response(result, ticker_metadata, text)

            # Calculate overall sentiment (weighted average)
            overall_score, overall_label = self._calculate_overall_sentiment(ticker_sentiments)

            return LLMSentimentResult(
                ticker_sentiments=ticker_sentiments,
                overall_sentiment_score=overall_score,
                overall_sentiment_label=overall_label,
                analysis_successful=True
            )

        except Exception as e:
            logger.error(f"LLM sentiment analysis failed: {e}")
            return LLMSentimentResult(
                ticker_sentiments=self._create_fallback_sentiments(ticker_metadata),
                overall_sentiment_score=0.0,
                overall_sentiment_label="neutral",
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

                # Parse raw confidence from LLM
                raw_confidence = float(raw.get('confidence', 0.5))
                raw_confidence = max(0.0, min(1.0, raw_confidence))

                # Get reasoning
                reasoning = raw.get('reasoning', 'No reasoning provided')

                # Apply confidence calibration to address LLM overconfidence
                calibrated_confidence = self._calibrate_confidence(
                    raw_confidence=raw_confidence,
                    sentiment_score=score,
                    text=text,
                    reasoning=reasoning,
                    num_tickers=num_tickers
                )

                ticker_sentiments[ticker] = {
                    'sentiment_score': round(score, 4),
                    'sentiment_label': label,
                    'confidence': round(calibrated_confidence, 4),
                    'raw_llm_confidence': round(raw_confidence, 4),  # Keep original for debugging
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

    def _calibrate_confidence(
        self,
        raw_confidence: float,
        sentiment_score: float,
        text: str,
        reasoning: str,
        num_tickers: int
    ) -> float:
        """
        Calibrate LLM confidence to be more realistic for trading decisions.

        LLMs tend to be overconfident (~90-95% always). This applies penalties based on:
        1. Base dampening (LLMs are systematically overconfident)
        2. Text length (shorter = less context = lower confidence)
        3. Number of tickers (more tickers = split attention = lower confidence)
        4. Sentiment extremity (extreme scores need more evidence)
        5. Reasoning quality (short reasoning = lower confidence)

        Returns:
            Calibrated confidence score (0.0 to 1.0)
        """
        confidence = raw_confidence

        # 1. Base dampening - LLMs are ~25-30% overconfident on average
        # This is the most important adjustment
        BASE_DAMPENING = 0.70  # Reduce all confidences by 30%
        confidence *= BASE_DAMPENING

        # 2. Text length penalty (less context = less certainty)
        word_count = len(text.split()) if text else 0
        if word_count < 15:
            confidence *= 0.65  # Very short text (tweets, headlines)
        elif word_count < 30:
            confidence *= 0.75  # Short text
        elif word_count < 50:
            confidence *= 0.85  # Medium-short text
        elif word_count > 150:
            confidence *= 1.08  # Longer text slightly more reliable
        # Cap at current value after potential boost
        confidence = min(confidence, raw_confidence * BASE_DAMPENING * 1.1)

        # 3. Multi-ticker penalty (attention split across tickers)
        if num_tickers > 1:
            # Each additional ticker reduces confidence
            # 2 tickers: 90%, 3 tickers: 82%, 4 tickers: 74%, etc.
            ticker_penalty = 1.0 - (0.10 * (num_tickers - 1))
            ticker_penalty = max(ticker_penalty, 0.55)  # Floor at 55%
            confidence *= ticker_penalty

        # 4. Extreme sentiment penalty (extreme claims need strong evidence)
        sentiment_extremity = abs(sentiment_score)
        if sentiment_extremity > 0.85:
            # Very extreme sentiments (>0.85 or <-0.85) should be rare
            confidence *= 0.80
        elif sentiment_extremity > 0.7:
            confidence *= 0.88
        elif sentiment_extremity > 0.5:
            confidence *= 0.95

        # 5. Reasoning quality check
        reasoning_words = len(reasoning.split()) if reasoning else 0
        if reasoning_words < 5:
            confidence *= 0.65  # Very short/no reasoning
        elif reasoning_words < 10:
            confidence *= 0.80  # Short reasoning
        elif reasoning_words > 25:
            confidence *= 1.05  # Detailed reasoning is good

        # 6. Neutral sentiment adjustment
        # Neutral predictions are often "safe defaults" when model is uncertain
        if abs(sentiment_score) < 0.1:
            confidence *= 0.85

        # Final bounds check
        # Cap at 0.85 (never fully confident), floor at 0.15 (always some signal)
        confidence = max(0.15, min(0.85, confidence))

        return confidence

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

    def _calculate_overall_sentiment(
        self,
        ticker_sentiments: Dict[str, Dict]
    ) -> tuple:
        """
        Calculate overall sentiment as weighted average.

        Returns:
            Tuple of (overall_score, overall_label)
        """
        if not ticker_sentiments:
            return 0.0, "neutral"

        # Weight by confidence
        total_weight = 0.0
        weighted_sum = 0.0

        for sentiment_data in ticker_sentiments.values():
            confidence = sentiment_data.get('confidence', 0.5)
            score = sentiment_data.get('sentiment_score', 0.0)
            weighted_sum += score * confidence
            total_weight += confidence

        if total_weight > 0:
            overall_score = round(weighted_sum / total_weight, 4)
        else:
            overall_score = 0.0

        overall_label = self._score_to_label(overall_score)

        return overall_score, overall_label

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
            'confidence': 0.0,
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

    # Test case simulating pipeline data
    test_item = {
        'content': {
            'clean_combined_withurl': """
            Apple just crushed earnings! Revenue up 15% YoY while Microsoft struggles
            with cloud growth slowdown. AAPL is going to the moon 🚀🚀🚀
            Meanwhile, MSFT looks bearish short-term. Diamond hands on Apple,
            but I'm selling my Microsoft position.
            """
        },
        'ticker_metadata': {
            'AAPL': {
                'OfficialName': 'Apple Inc.',
                'event_type': 'Earnings Report'
            },
            'MSFT': {
                'OfficialName': 'Microsoft Corporation',
                'event_type': 'Earnings Report'
            }
        }
    }

    service = LLMSentimentService()

    print("\nAnalyzing test item...\n")
    result = await service.analyse(test_item)

    print("Results:")
    print("-" * 80)

    sentiment_analysis = result.get('sentiment_analysis', {})
    print(f"Overall Score: {sentiment_analysis.get('overall_sentiment_score')}")
    print(f"Overall Label: {sentiment_analysis.get('overall_sentiment_label')}")
    print(f"Analysis Successful: {sentiment_analysis.get('analysis_successful')}")

    print("\nPer-Ticker Sentiments:")
    for ticker, data in sentiment_analysis.get('ticker_sentiments', {}).items():
        print(f"\n  {ticker} ({data.get('official_name')}):")
        print(f"    Score: {data.get('sentiment_score')}")
        print(f"    Label: {data.get('sentiment_label')}")
        print(f"    Raw LLM Confidence: {data.get('raw_llm_confidence')} (before calibration)")
        print(f"    Calibrated Confidence: {data.get('confidence')} (after calibration)")
        print(f"    Reasoning: {data.get('reasoning')}")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
