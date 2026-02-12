"""
Sentiment Analysis Service - Integrated with News Analysis Pipeline
File: news-analysis/app/services/_05_sentiment.py

IMPROVED VERSION with Adaptive Emoji Weighting
"""

import re
import emoji
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

import numpy as np
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Import config from your existing structure
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging
logger = logging.getLogger(__name__)


class SentimentLabel(Enum):
    """Sentiment classification labels"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class SentimentResult:
    """Structured sentiment analysis result matching your JSON schema"""
    sentiment_label: str
    sentiment_score: float  # Range: -1.0 to 1.0
    confidence: float
    positive_prob: float
    negative_prob: float
    neutral_prob: float
    emoji_influence: float
    models_used: List[str]
    method_used: str
    reasoning: str = ""  # Explanation of sentiment factors


class EmojiSentimentAnalyzer:
    """Handles emoji-specific sentiment analysis for financial content"""

    # Financial/trading emoji sentiment mappings (curated for Reddit WSB, r/stocks)
    EMOJI_SENTIMENT_MAP = {
        # Bullish emojis
        '📈': 0.8, '🚀': 0.9, '💎': 0.7, '🙌': 0.6, '💰': 0.7,
        '🤑': 0.8, '💵': 0.6, '💸': 0.5, '📊': 0.4, '✅': 0.6,
        '👍': 0.5, '🔥': 0.7, '🌙': 0.6, '⬆️': 0.7, '🐂': 0.7,
        '💪': 0.6, '🎉': 0.6, '🎊': 0.6, '⭐': 0.5, '🏆': 0.7,

        # Bearish emojis
        '📉': -0.8, '💩': -0.8, '🤡': -0.7, '⬇️': -0.7, '😭': -0.6,
        '😢': -0.5, '💀': -0.7, '🩸': -0.8, '🔻': -0.7, '❌': -0.6,
        '👎': -0.5, '🚨': -0.6, '⚠️': -0.5, '🐻': -0.7, '😡': -0.6,
        '🤮': -0.7, '😱': -0.6, '💔': -0.6, '⚰️': -0.8, '🧻': -0.5,
        '👋': -0.3,

        # Neutral
        '🤔': 0.0, '👀': 0.0, '💭': 0.0, '❓': 0.0, '🤷': 0.0,
        '😐': 0.0, '😶': 0.0, '🧐': 0.0,
    }

    def __init__(self):
        self.vader = SentimentIntensityAnalyzer()

        # Update VADER lexicon with Reddit financial slang
        financial_slang = {
            # WSB/Reddit specific - INCREASED SCORES
            'moon': 3.5, 'mooning': 4.0, 'rocket': 3.5, 'rockets': 3.5,
            'tendies': 3.0, 'stonks': 2.5, 'stonk': 2.5,
            'diamond hands': 3.5, 'diamondhands': 3.5,
            'paper hands': -3.0, 'paperhands': -3.0,
            'hodl': 2.5, 'hodling': 2.5,
            'yolo': 2.5, 'ape': 2.0, 'apes': 2.0,
            'dd': 1.5, 'btfd': 2.5,
            'bagholder': -3.0, 'bagholding': -3.0, 'bags': -2.5,
            'fud': -3.0, 'fomo': 2.0,
            'rekt': -3.5, 'rug': -3.5, 'rugpull': -3.5,
            'pump': 2.5, 'dump': -3.0,
            'short squeeze': 3.0, 'gamma squeeze': 3.0, 'squeeze': 2.5,

            # Financial terms
            'bullish': 3.0, 'bearish': -3.0, 'bull': 2.5, 'bear': -2.5,
            'rally': 2.5, 'crash': -3.5, 'dip': -1.5, 'rip': 3.0,
            'moon shot': 3.5, 'to the moon': 4.0,
            'buy the dip': 2.0, 'btd': 2.0,
        }
        self.vader.lexicon.update(financial_slang)

    def extract_emojis(self, text: str) -> List[str]:
        """Extract all emojis from text"""
        return [char for char in text if char in emoji.EMOJI_DATA]

    def calculate_emoji_sentiment(self, emojis: List[str]) -> tuple[float, int]:
        """Calculate aggregate emoji sentiment. Returns (score, count)"""
        if not emojis:
            return 0.0, 0

        scores = []
        for em in emojis:
            if em in self.EMOJI_SENTIMENT_MAP:
                scores.append(self.EMOJI_SENTIMENT_MAP[em])
            else:
                # Fallback to VADER for unmapped emojis
                vader_score = self.vader.polarity_scores(em)['compound']
                scores.append(vader_score)

        return np.mean(scores) if scores else 0.0, len(emojis)

    def analyze_with_vader(self, text: str) -> float:
        """Analyze text with VADER for slang detection"""
        scores = self.vader.polarity_scores(text)
        return scores['compound']

    def remove_emojis(self, text: str) -> str:
        """Remove emojis from text"""
        text = emoji.replace_emoji(text, replace='')
        text = re.sub(r':[a-z_]+:', '', text)
        return text


class SentimentAnalysisService:
    """Main sentiment analysis service with Adaptive Weighting"""

    _instance = None

    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super(SentimentAnalysisService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        logger.info("Initializing Sentiment Analysis Service...")

        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"Using device: {self.device}")

        model_name = "ProsusAI/finbert"
        logger.info(f"Loading model: {model_name}")

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()
            logger.info("FinBERT model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load FinBERT model: {e}")
            raise

        self.emoji_analyzer = EmojiSentimentAnalyzer()
        self.id2label = {0: "positive", 1: "negative", 2: "neutral"}

        self._initialized = True
        logger.info("Sentiment Analysis Service initialized successfully")

    def preprocess_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        text = ' '.join(text.split())
        return text.strip()

    def calculate_adaptive_weights(
        self,
        text: str,
        emoji_count: int,
        base_emoji_weight: float = 0.3
    ) -> tuple[float, float]:
        """
        Calculate adaptive weights based on text characteristics

        Rules:
        1. High emoji density → Increase emoji weight
        2. Short text with emojis → Increase emoji weight
        3. Long formal text → Decrease emoji weight
        """
        text_length = len(text.split())

        # Calculate emoji density (emojis per 10 words)
        emoji_density = (emoji_count / max(text_length, 1)) * 10

        # Adaptive weighting rules
        if emoji_count == 0:
            # No emojis - pure text
            return 0.0, 1.0

        elif text_length <= 5 and emoji_count >= 2:
            # Very short text with multiple emojis (e.g., "🚀🚀🚀")
            # Give emojis much more weight
            emoji_weight = 0.6
            text_weight = 0.4

        elif text_length <= 10 and emoji_count >= 3:
            # Short text with many emojis (e.g., "To the moon! 🚀🚀🚀")
            # Boost emoji influence
            emoji_weight = 0.55
            text_weight = 0.45

        elif emoji_density >= 2.0:
            # High emoji density
            emoji_weight = 0.5
            text_weight = 0.5

        elif emoji_density >= 1.0:
            # Moderate emoji density
            emoji_weight = 0.4
            text_weight = 0.6

        elif text_length > 50:
            # Long text - reduce emoji influence
            emoji_weight = 0.2
            text_weight = 0.8

        else:
            # Default balanced
            emoji_weight = base_emoji_weight
            text_weight = 1.0 - base_emoji_weight

        # Normalize
        total = emoji_weight + text_weight
        return emoji_weight / total, text_weight / total

    def analyze_with_finbert(self, text: str) -> Dict[str, float]:
        """Analyze text using FinBERT model"""
        if not text or not text.strip():
            return {'positive': 0.33, 'negative': 0.33, 'neutral': 0.34}

        try:
            inputs = self.tokenizer(
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)

            probs = probs.cpu().numpy()[0]

            return {
                'positive': float(probs[0]),
                'negative': float(probs[1]),
                'neutral': float(probs[2])
            }
        except Exception as e:
            logger.error(f"FinBERT analysis failed: {e}")
            return {'positive': 0.33, 'negative': 0.33, 'neutral': 0.34}

    def analyze_text(
        self,
        text: str,
        emoji_weight: Optional[float] = None,
        text_weight: Optional[float] = None,
        use_adaptive_weights: bool = True
    ) -> SentimentResult:
        """
        Main analysis method with adaptive weighting

        Args:
            text: Input text to analyze
            emoji_weight: Manual emoji weight (overrides adaptive)
            text_weight: Manual text weight (overrides adaptive)
            use_adaptive_weights: Use adaptive weighting system
        """
        if not text or not text.strip():
            logger.warning("Empty text provided")
            return self._create_neutral_result()

        processed_text = self.preprocess_text(text)

        # Extract emojis
        emojis = self.emoji_analyzer.extract_emojis(processed_text)
        emoji_score, emoji_count = self.emoji_analyzer.calculate_emoji_sentiment(emojis)

        # Remove emojis for text analysis
        text_only = self.emoji_analyzer.remove_emojis(processed_text)

        # Determine weights
        if emoji_weight is not None and text_weight is not None:
            # Manual weights provided
            total = emoji_weight + text_weight
            final_emoji_weight = emoji_weight / total
            final_text_weight = text_weight / total
            method_suffix = "_manual"
        elif use_adaptive_weights and emoji_count > 0:
            # Use adaptive weighting
            final_emoji_weight, final_text_weight = self.calculate_adaptive_weights(
                text_only, emoji_count
            )
            method_suffix = "_adaptive"
        else:
            # Default weights
            final_emoji_weight = 0.3 if emoji_count > 0 else 0.0
            final_text_weight = 0.7 if emoji_count > 0 else 1.0
            method_suffix = "_default"

        models_used = []

        # Analyze text with FinBERT
        if text_only.strip():
            finbert_scores = self.analyze_with_finbert(text_only)
            models_used.append("FinBERT")

            # ALSO analyze with VADER for slang detection
            vader_compound = self.emoji_analyzer.analyze_with_vader(text_only)

            # If VADER detects strong sentiment in slang, boost it
            if abs(vader_compound) > 0.5:
                models_used.append("VADER")
                # Blend FinBERT with VADER for slang-heavy text

                if vader_compound > 0:
                    finbert_scores['positive'] = (
                        0.7 * finbert_scores['positive'] +
                        0.3 * (0.5 + vader_compound/2)
                    )
                    finbert_scores['negative'] = (
                        0.7 * finbert_scores['negative'] +
                        0.3 * 0.25
                    )
                else:
                    finbert_scores['negative'] = (
                        0.7 * finbert_scores['negative'] +
                        0.3 * (0.5 - vader_compound/2)
                    )
                    finbert_scores['positive'] = (
                        0.7 * finbert_scores['positive'] +
                        0.3 * 0.25
                    )

                # Renormalize
                total = sum(finbert_scores.values())
                finbert_scores = {k: v/total for k, v in finbert_scores.items()}

            method_used = f"finbert+emoji{method_suffix}" if emojis else "finbert_only"
        else:
            finbert_scores = {'positive': 0.33, 'negative': 0.33, 'neutral': 0.34}
            method_used = "emoji_only"

        if emoji_count > 0:
            models_used.append("Emoji")

        # Combine scores
        if emoji_count > 0 and text_only.strip():
            emoji_probs = self._emoji_score_to_probs(emoji_score, strength=1.5)

            final_positive = (final_text_weight * finbert_scores['positive'] +
                            final_emoji_weight * emoji_probs['positive'])
            final_negative = (final_text_weight * finbert_scores['negative'] +
                            final_emoji_weight * emoji_probs['negative'])
            final_neutral = (final_text_weight * finbert_scores['neutral'] +
                           final_emoji_weight * emoji_probs['neutral'])
            emoji_influence = final_emoji_weight

        elif emoji_count > 0:
            emoji_probs = self._emoji_score_to_probs(emoji_score, strength=1.5)
            final_positive = emoji_probs['positive']
            final_negative = emoji_probs['negative']
            final_neutral = emoji_probs['neutral']
            emoji_influence = 1.0

        else:
            final_positive = finbert_scores['positive']
            final_negative = finbert_scores['negative']
            final_neutral = finbert_scores['neutral']
            emoji_influence = 0.0

        # Determine label with more aggressive thresholds
        label, confidence = self._determine_label_and_confidence(
            final_positive, final_negative, final_neutral,
            threshold=0.05  # Reduced from 0.1 for more decisive results
        )

        # Calculate sentiment score with explicit clamping to [-1, 1]
        sentiment_score = max(-1.0, min(1.0, final_positive - final_negative))

        # Build reasoning string
        reasoning_parts = []

        # Emoji influence reasoning
        if emoji_count > 0:
            emoji_sentiment_desc = "bullish" if emoji_score > 0.2 else "bearish" if emoji_score < -0.2 else "mixed"
            reasoning_parts.append(
                f"Found {emoji_count} emojis ({emoji_sentiment_desc}, influence: {emoji_influence:.0%})"
            )

        # VADER slang detection reasoning
        if "VADER" in models_used:
            reasoning_parts.append("Financial slang detected (VADER boost applied)")

        # FinBERT reasoning
        if "FinBERT" in models_used:
            if finbert_scores['positive'] > 0.7:
                reasoning_parts.append(f"Strong positive language (FinBERT: {finbert_scores['positive']:.2f})")
            elif finbert_scores['negative'] > 0.7:
                reasoning_parts.append(f"Strong negative language (FinBERT: {finbert_scores['negative']:.2f})")
            elif finbert_scores['neutral'] > 0.6:
                reasoning_parts.append(f"Neutral/factual language (FinBERT: {finbert_scores['neutral']:.2f})")
            else:
                reasoning_parts.append(f"Mixed signals (pos: {finbert_scores['positive']:.2f}, neg: {finbert_scores['negative']:.2f})")

        # Final sentiment reasoning
        if label == "positive":
            reasoning_parts.append(f"Overall positive sentiment (score: {sentiment_score:.2f})")
        elif label == "negative":
            reasoning_parts.append(f"Overall negative sentiment (score: {sentiment_score:.2f})")
        else:
            reasoning_parts.append(f"Neutral/uncertain sentiment (score: {sentiment_score:.2f})")

        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Standard analysis"

        return SentimentResult(
            sentiment_label=label,
            sentiment_score=sentiment_score,
            confidence=confidence,
            positive_prob=final_positive,
            negative_prob=final_negative,
            neutral_prob=final_neutral,
            emoji_influence=emoji_influence,
            models_used=models_used,
            method_used=method_used,
            reasoning=reasoning
        )

    def _emoji_score_to_probs(self, emoji_score: float, strength: float = 1.0) -> Dict[str, float]:
        """
        Convert emoji score to probability distribution
        strength: multiplier for emoji influence (>1 = stronger)
        """
        # Apply strength multiplier
        emoji_score = emoji_score * strength

        if emoji_score > 0.15:  # Lowered threshold
            return {
                'positive': min(0.5 + emoji_score/2, 0.95),
                'negative': max(0.025, 0.2 - emoji_score/2),
                'neutral': 0.025
            }
        elif emoji_score < -0.15:  # Lowered threshold
            return {
                'positive': max(0.025, 0.2 + emoji_score/2),
                'negative': min(0.5 - emoji_score/2, 0.95),
                'neutral': 0.025
            }
        else:
            return {'positive': 0.35, 'negative': 0.35, 'neutral': 0.30}

    def _determine_label_and_confidence(
        self,
        positive: float,
        negative: float,
        neutral: float,
        threshold: float = 0.05
    ) -> tuple[str, float]:
        """Determine sentiment label and confidence score"""
        max_score = max(positive, negative, neutral)

        # More aggressive classification
        if neutral == max_score:
            # Only return neutral if it significantly dominates
            if neutral - max(positive, negative) > threshold * 2:
                return "neutral", neutral
            # Otherwise, pick the stronger of pos/neg
            elif positive > negative:
                return "positive", positive
            else:
                return "negative", negative

        # If pos/neg difference is tiny, check if we should default to neutral
        if abs(positive - negative) < threshold and neutral > 0.3:
            return "neutral", neutral

        if positive == max_score:
            return "positive", positive
        elif negative == max_score:
            return "negative", negative
        else:
            return "neutral", neutral

    def _create_neutral_result(self) -> SentimentResult:
        """Create neutral result for edge cases"""
        return SentimentResult(
            sentiment_label="neutral",
            sentiment_score=0.0,
            confidence=0.34,
            positive_prob=0.33,
            negative_prob=0.33,
            neutral_prob=0.34,
            emoji_influence=0.0,
            models_used=[],
            method_used="default"
        )

    def process_batch(self, items: List[Dict]) -> List[Dict]:
        """Process batch of items from pipeline"""
        logger.info(f"Processing batch of {len(items)} items for sentiment analysis")

        results = []
        for item in items:
            try:
                text = item.get('clean_combined', '') or item.get('clean_title', '')

                sentiment = self.analyze_text(text, use_adaptive_weights=True)

                item['sentiment_score'] = round(sentiment.sentiment_score, 6)
                item['sentiment_label'] = sentiment.sentiment_label
                item['confidence'] = round(sentiment.confidence, 6)
                item['models_used'] = sentiment.models_used

                results.append(item)

            except Exception as e:
                logger.error(f"Failed to analyze item {item.get('Post_ID', 'unknown')}: {e}")
                item['sentiment_score'] = 0.0
                item['sentiment_label'] = "neutral"
                item['confidence'] = 0.0
                item['models_used'] = []
                results.append(item)

        logger.info(f"Completed sentiment analysis for {len(results)} items")
        return results

    def analyse(self, item: Dict) -> Dict:
        """
        Analyze a single item for sentiment (synchronous).
        Returns the item enriched with sentiment scores.
        Handles nested pipeline data structure.
        """
        try:
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

            sentiment = self.analyze_text(text, use_adaptive_weights=True)

            # Enrich item with sentiment data
            item['sentiment_score'] = round(sentiment.sentiment_score, 6)
            item['sentiment_label'] = sentiment.sentiment_label
            item['sentiment_confidence'] = round(sentiment.confidence, 6)
            item['positive_prob'] = round(sentiment.positive_prob, 6)
            item['negative_prob'] = round(sentiment.negative_prob, 6)
            item['neutral_prob'] = round(sentiment.neutral_prob, 6)
            item['emoji_influence'] = round(sentiment.emoji_influence, 6)
            item['models_used'] = sentiment.models_used
            item['method_used'] = sentiment.method_used
            item['sentiment_reasoning'] = sentiment.reasoning

            return item

        except Exception as e:
            logger.error(f"Sentiment analysis failed for {item.get('Post_ID', 'unknown')}: {e}")
            item['sentiment_score'] = 0.0
            item['sentiment_label'] = "neutral"
            item['sentiment_confidence'] = 0.0
            item['models_used'] = []
            item['sentiment_reasoning'] = f"Analysis error: {str(e)}"
            return item

    def _extract_ticker_context(
        self,
        text: str,
        ticker: str,
        ticker_info: Dict,
        context_sentences: int = 2
    ) -> str:
        """
        Extract sentences mentioning a specific ticker or company.

        Args:
            text: Full text to search
            ticker: Stock ticker symbol (e.g., "AAPL")
            ticker_info: Ticker metadata with OfficialName and NameIdentified
            context_sentences: Number of sentences around mention to include

        Returns:
            Extracted context text for this ticker
        """
        if not text:
            return ""

        # Build search terms from ticker info
        search_terms = [ticker.upper(), ticker.lower(), f"${ticker.upper()}"]

        # Add official name and identified names
        official_name = ticker_info.get('OfficialName', '')
        if official_name:
            search_terms.append(official_name)
            # Also add partial name (first word for multi-word companies)
            first_word = official_name.split()[0] if official_name else ''
            if len(first_word) > 3:
                search_terms.append(first_word)

        names_identified = ticker_info.get('NameIdentified', [])
        if isinstance(names_identified, list):
            search_terms.extend(names_identified)

        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # Find sentences containing any search term
        relevant_indices = set()
        for i, sentence in enumerate(sentences):
            sentence_lower = sentence.lower()
            for term in search_terms:
                if term.lower() in sentence_lower:
                    # Add this sentence and context
                    for j in range(max(0, i - context_sentences), min(len(sentences), i + context_sentences + 1)):
                        relevant_indices.add(j)
                    break

        if not relevant_indices:
            # No specific mention found, return full text (ticker may be implied)
            return text

        # Build context from relevant sentences
        relevant_sentences = [sentences[i] for i in sorted(relevant_indices)]
        return ". ".join(relevant_sentences)

    def analyse_per_ticker(self, item: Dict) -> Dict:
        """
        Analyze sentiment for each ticker mentioned in the post.
        Processes ALL tickers with no limit.

        Args:
            item: Post data with ticker_metadata

        Returns:
            Item enriched with ticker_sentiments dict
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
            # No tickers identified - just do overall sentiment
            item['ticker_sentiments'] = {}
            return self.analyse(item)

        ticker_sentiments = {}

        for ticker, info in ticker_metadata.items():
            try:
                # Extract context for this ticker
                ticker_context = self._extract_ticker_context(full_text, ticker, info)

                # Analyze sentiment for this context
                sentiment = self.analyze_text(ticker_context, use_adaptive_weights=True)

                ticker_sentiments[ticker] = {
                    'sentiment_label': sentiment.sentiment_label,
                    'sentiment_score': round(sentiment.sentiment_score, 6),
                    'confidence': round(sentiment.confidence, 6),
                    'reasoning': sentiment.reasoning,
                    'context_length': len(ticker_context.split()),
                    'official_name': info.get('OfficialName', ticker)
                }

            except Exception as e:
                logger.error(f"Per-ticker sentiment failed for {ticker}: {e}")
                ticker_sentiments[ticker] = {
                    'sentiment_label': 'neutral',
                    'sentiment_score': 0.0,
                    'confidence': 0.0,
                    'reasoning': f"Analysis error: {str(e)}",
                    'official_name': info.get('OfficialName', ticker)
                }

        item['ticker_sentiments'] = ticker_sentiments

        # Also compute overall sentiment
        item = self.analyse(item)

        # Add summary stats
        if ticker_sentiments:
            scores = [ts['sentiment_score'] for ts in ticker_sentiments.values()]
            item['ticker_sentiment_avg'] = round(sum(scores) / len(scores), 6)
            item['ticker_sentiment_count'] = len(ticker_sentiments)

        return item


# Singleton instance
sentiment_service = SentimentAnalysisService()
