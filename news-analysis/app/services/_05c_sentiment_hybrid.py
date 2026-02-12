"""
Hybrid Sentiment Analysis Service - Combining FinBERT and LLM
File: news-analysis/app/services/_05c_sentiment_hybrid.py

Ensemble approach combining:
- FinBERT: Fast, reliable for standard financial text
- LLM: Better reasoning, catches nuance and sarcasm
"""

import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

# Import the individual services
from app.services._05_sentiment import SentimentAnalysisService, SentimentResult
from app.services._05b_sentiment_llm import LLMSentimentService, LLMSentimentResult

# Import config
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import env_config

logger = logging.getLogger(__name__)


@dataclass
class HybridSentimentResult:
    """Combined sentiment result from both models"""
    # Final combined values
    sentiment_label: str
    sentiment_score: float  # -1.0 to 1.0
    confidence: float
    reasoning: str

    # Individual model scores
    finbert_score: float
    finbert_label: str
    finbert_confidence: float

    llm_score: float
    llm_label: str
    llm_confidence: float
    llm_reasoning: str
    llm_factors: List[str]

    # Metadata
    agreement: bool  # Whether both models agree on label
    models_used: List[str]
    weights_used: Dict[str, float]


class HybridSentimentService:
    """
    Hybrid sentiment analysis combining FinBERT and LLM.

    Default weights:
    - FinBERT: 60% (fast, reliable for standard text)
    - LLM: 40% (better reasoning, catches nuance)

    When models disagree, adjusts weights based on confidence.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        finbert_weight: float = 0.6,
        llm_weight: float = 0.4,
        use_confidence_weighting: bool = True
    ):
        if self._initialized:
            return

        logger.info("Initializing Hybrid Sentiment Service...")

        # Initialize component services
        self.finbert_service = SentimentAnalysisService()
        self.llm_service = LLMSentimentService()

        # Default weights (should sum to 1.0)
        self.default_finbert_weight = finbert_weight
        self.default_llm_weight = llm_weight
        self.use_confidence_weighting = use_confidence_weighting

        self._initialized = True
        logger.info(
            f"Hybrid Service initialized (FinBERT: {finbert_weight:.0%}, LLM: {llm_weight:.0%})"
        )

    async def analyze(
        self,
        text: str,
        finbert_weight: Optional[float] = None,
        llm_weight: Optional[float] = None
    ) -> HybridSentimentResult:
        """
        Analyze sentiment using both FinBERT and LLM, then combine.

        Args:
            text: Text to analyze
            finbert_weight: Override default FinBERT weight
            llm_weight: Override default LLM weight

        Returns:
            HybridSentimentResult with combined analysis
        """
        if not text or not text.strip():
            return self._create_empty_result()

        # Set weights
        fb_weight = finbert_weight if finbert_weight is not None else self.default_finbert_weight
        lm_weight = llm_weight if llm_weight is not None else self.default_llm_weight

        # Normalize weights
        total = fb_weight + lm_weight
        fb_weight = fb_weight / total
        lm_weight = lm_weight / total

        # Run both analyses in parallel
        finbert_task = asyncio.to_thread(self.finbert_service.analyze_text, text)
        llm_task = self.llm_service.analyze(text)

        finbert_result, llm_result = await asyncio.gather(finbert_task, llm_task)

        # Combine results
        return self._combine_results(
            finbert_result,
            llm_result,
            fb_weight,
            lm_weight
        )

    def analyze_sync(self, text: str) -> HybridSentimentResult:
        """
        Synchronous wrapper for analyze().
        """
        return asyncio.run(self.analyze(text))

    async def analyse(self, item: Dict) -> Dict:
        """
        Analyze a single item using hybrid approach.
        Returns the item enriched with combined sentiment data.
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

        # Enrich item with hybrid sentiment data
        item['sentiment_score'] = result.sentiment_score
        item['sentiment_label'] = result.sentiment_label
        item['sentiment_confidence'] = result.confidence
        item['sentiment_reasoning'] = result.reasoning

        # Also include individual model results
        item['finbert_score'] = result.finbert_score
        item['finbert_label'] = result.finbert_label
        item['llm_score'] = result.llm_score
        item['llm_label'] = result.llm_label
        item['llm_reasoning'] = result.llm_reasoning
        item['llm_factors'] = result.llm_factors

        item['models_agreement'] = result.agreement
        item['models_used'] = result.models_used
        item['weights_used'] = result.weights_used

        return item

    async def analyse_per_ticker(self, item: Dict) -> Dict:
        """
        Analyze sentiment for each ticker using hybrid approach.
        """
        ticker_metadata = item.get('ticker_metadata', {})

        # Extract full text
        content = item.get('content', {})
        full_text = (
            content.get('clean_combined_withurl', '') or
            content.get('clean_combined_withouturl', '') or
            content.get('clean_combined', '') or
            item.get('clean_combined', '') or
            ''
        )

        if not ticker_metadata:
            item['ticker_sentiments'] = {}
            return await self.analyse(item)

        ticker_sentiments = {}

        for ticker, info in ticker_metadata.items():
            try:
                # Use FinBERT's context extraction
                ticker_context = self.finbert_service._extract_ticker_context(
                    full_text, ticker, info
                )

                # Analyze with hybrid approach
                result = await self.analyze(ticker_context)

                ticker_sentiments[ticker] = {
                    'sentiment_label': result.sentiment_label,
                    'sentiment_score': result.sentiment_score,
                    'confidence': result.confidence,
                    'reasoning': result.reasoning,
                    'finbert_score': result.finbert_score,
                    'llm_score': result.llm_score,
                    'models_agree': result.agreement,
                    'official_name': info.get('OfficialName', ticker)
                }

            except Exception as e:
                logger.error(f"Hybrid per-ticker analysis failed for {ticker}: {e}")
                ticker_sentiments[ticker] = {
                    'sentiment_label': 'neutral',
                    'sentiment_score': 0.0,
                    'confidence': 0.0,
                    'reasoning': f"Analysis error: {str(e)}",
                    'official_name': info.get('OfficialName', ticker)
                }

        item['ticker_sentiments'] = ticker_sentiments

        # Also compute overall sentiment
        item = await self.analyse(item)

        # Add summary
        if ticker_sentiments:
            scores = [ts['sentiment_score'] for ts in ticker_sentiments.values()]
            item['ticker_sentiment_avg'] = round(sum(scores) / len(scores), 6)
            item['ticker_sentiment_count'] = len(ticker_sentiments)

        return item

    def _combine_results(
        self,
        finbert: SentimentResult,
        llm: LLMSentimentResult,
        fb_weight: float,
        lm_weight: float
    ) -> HybridSentimentResult:
        """
        Combine FinBERT and LLM results with weighted averaging.
        """
        # Check if models agree on label
        agreement = finbert.sentiment_label == llm.sentiment_label

        # Adjust weights based on confidence if models disagree
        final_fb_weight = fb_weight
        final_lm_weight = lm_weight

        if self.use_confidence_weighting and not agreement:
            # Weight by confidence when models disagree
            total_conf = finbert.confidence + llm.confidence
            if total_conf > 0:
                conf_fb_weight = finbert.confidence / total_conf
                conf_lm_weight = llm.confidence / total_conf

                # Blend default weights with confidence weights (50/50)
                final_fb_weight = 0.5 * fb_weight + 0.5 * conf_fb_weight
                final_lm_weight = 0.5 * lm_weight + 0.5 * conf_lm_weight

                # Renormalize
                total = final_fb_weight + final_lm_weight
                final_fb_weight /= total
                final_lm_weight /= total

        # Calculate combined score
        combined_score = (
            final_fb_weight * finbert.sentiment_score +
            final_lm_weight * llm.sentiment_score
        )
        combined_score = max(-1.0, min(1.0, combined_score))

        # Determine final label
        if combined_score > 0.1:
            final_label = "positive"
        elif combined_score < -0.1:
            final_label = "negative"
        else:
            final_label = "neutral"

        # Combine confidence (weighted average)
        combined_confidence = (
            final_fb_weight * finbert.confidence +
            final_lm_weight * llm.confidence
        )

        # Build combined reasoning
        if agreement:
            reasoning = f"Both models agree: {llm.reasoning}"
        else:
            reasoning = (
                f"Models disagree (FinBERT: {finbert.sentiment_label}, "
                f"LLM: {llm.sentiment_label}). Combined analysis: {llm.reasoning}"
            )

        return HybridSentimentResult(
            sentiment_label=final_label,
            sentiment_score=round(combined_score, 6),
            confidence=round(combined_confidence, 6),
            reasoning=reasoning,

            finbert_score=round(finbert.sentiment_score, 6),
            finbert_label=finbert.sentiment_label,
            finbert_confidence=round(finbert.confidence, 6),

            llm_score=round(llm.sentiment_score, 6),
            llm_label=llm.sentiment_label,
            llm_confidence=round(llm.confidence, 6),
            llm_reasoning=llm.reasoning,
            llm_factors=llm.key_factors,

            agreement=agreement,
            models_used=["FinBERT", f"LLM-{env_config.large_language_model_gemini or 'llama3:8b'}"],
            weights_used={
                "finbert": round(final_fb_weight, 3),
                "llm": round(final_lm_weight, 3)
            }
        )

    def _create_empty_result(self) -> HybridSentimentResult:
        """Create neutral result for empty input."""
        return HybridSentimentResult(
            sentiment_label="neutral",
            sentiment_score=0.0,
            confidence=0.0,
            reasoning="Empty text",

            finbert_score=0.0,
            finbert_label="neutral",
            finbert_confidence=0.0,

            llm_score=0.0,
            llm_label="neutral",
            llm_confidence=0.0,
            llm_reasoning="Empty text",
            llm_factors=[],

            agreement=True,
            models_used=[],
            weights_used={"finbert": 0.6, "llm": 0.4}
        )


# Singleton instance
hybrid_sentiment_service = HybridSentimentService()


# Main for testing
async def main():
    print("="*80)
    print("HYBRID SENTIMENT SERVICE TEST")
    print("="*80)

    test_texts = [
        # Clear positive
        "AAPL just crushed earnings! Revenue up 15% YoY. 🚀🚀🚀 To the moon!",

        # Clear negative
        "This stock is going to dump hard. Management is incompetent. Sell everything.",

        # Neutral/factual
        "Apple Inc reported Q4 earnings of $1.50 per share, meeting analyst expectations.",

        # Reddit slang (FinBERT may miss nuance)
        "Diamond hands! 💎🙌 HODL through the dip, tendies coming soon!",

        # Sarcasm (LLM should catch)
        "Yeah sure, this company will definitely 10x next year. Just like my last 5 picks. 🤡",

        # Mixed signals
        "The earnings beat expectations but guidance was disappointing. Stock down 5% AH.",
    ]

    service = HybridSentimentService()

    print("\nAnalyzing test texts...\n")

    for i, text in enumerate(test_texts, 1):
        print(f"Test {i}: {text[:60]}...")
        result = await service.analyze(text)

        print("  Combined:")
        print(f"    Label: {result.sentiment_label}")
        print(f"    Score: {result.sentiment_score}")
        print(f"    Confidence: {result.confidence}")

        print(f"  FinBERT: {result.finbert_label} ({result.finbert_score:.2f})")
        print(f"  LLM: {result.llm_label} ({result.llm_score:.2f})")
        print(f"  Agreement: {result.agreement}")
        print(f"  Weights: FB={result.weights_used['finbert']:.2f}, LLM={result.weights_used['llm']:.2f}")
        print(f"  Reasoning: {result.reasoning[:100]}...")
        print("-"*80)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
