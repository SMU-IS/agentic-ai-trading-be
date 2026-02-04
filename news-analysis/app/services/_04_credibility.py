"""
Credibility Service - Hybrid Heuristic + LLM Approach
File: news-analysis/app/services/_04_credibility.py

Uses both heuristic scoring AND Ollama LLM for credibility analysis.
"""

import asyncio
import json
import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

# Import config
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import env_config

logger = logging.getLogger(__name__)


class SourceTier(Enum):
    """Source reliability tiers"""
    TIER_1_PREMIUM = "tier_1_premium"
    TIER_2_REPUTABLE = "tier_2_reputable"
    TIER_3_SOCIAL = "tier_3_social"
    TIER_4_UNKNOWN = "tier_4_unknown"


@dataclass
class CredibilityScore:
    """Credibility analysis result"""
    overall_score: float
    source_score: float
    author_score: float
    content_score: float
    source_tier: str
    source_name: str
    confidence: float
    warnings: List[str]
    details: Dict
    llm_analysis: Optional[Dict] = None


class SourceCredibilityEvaluator:
    """Evaluates source credibility from domain/URL"""

    # Tier 1: Premium financial sources (0.90-1.0)
    TIER_1_SOURCES = {
        'reuters.com': {'score': 0.95, 'name': 'Reuters'},
        'wsj.com': {'score': 0.95, 'name': 'Wall Street Journal'},
        'ft.com': {'score': 0.94, 'name': 'Financial Times'},
        'bloomberg.com': {'score': 0.94, 'name': 'Bloomberg'},
        'federalreserve.gov': {'score': 1.0, 'name': 'Federal Reserve'},
        'sec.gov': {'score': 1.0, 'name': 'SEC'},
        'treasury.gov': {'score': 1.0, 'name': 'US Treasury'},
    }

    # Tier 2: Reputable financial sources (0.75-0.85)
    TIER_2_SOURCES = {
        'cnbc.com': {'score': 0.85, 'name': 'CNBC'},
        'businessinsider.com': {'score': 0.75, 'name': 'Business Insider'},
        'finance.yahoo.com': {'score': 0.78, 'name': 'Yahoo Finance'},
        'marketwatch.com': {'score': 0.78, 'name': 'MarketWatch'},
        'forbes.com': {'score': 0.77, 'name': 'Forbes'},
        'economist.com': {'score': 0.85, 'name': 'The Economist'},
        'barrons.com': {'score': 0.82, 'name': "Barron's"},
    }

    # Tier 3: Social media (0.30-0.70, adjusted by subreddit/user)
    TIER_3_SOURCES = {
        'reddit.com': {'score': 0.50, 'name': 'Reddit'},
        'x.com': {'score': 0.45, 'name': 'X'},
    }

    # Reddit subreddit modifiers
    SUBREDDIT_MODIFIERS = {
        'investing': 0.70,
        'stocks': 0.60,
        'wallstreetbets': 0.30,
        'cryptocurrency': 0.35,
        'finance': 0.65,
    }

    @classmethod
    def evaluate(cls, domain: str, subreddit: Optional[str] = None) -> Tuple[float, str, str]:
        """
        Evaluate source credibility
        Returns: (score, tier, name)
        """
        if not domain:
            return 0.3, SourceTier.TIER_4_UNKNOWN.value, "Unknown"

        domain = domain.lower().replace('www.', '')

        # Check Tier 1
        if domain in cls.TIER_1_SOURCES:
            info = cls.TIER_1_SOURCES[domain]
            return info['score'], SourceTier.TIER_1_PREMIUM.value, info['name']

        # Check Tier 2
        if domain in cls.TIER_2_SOURCES:
            info = cls.TIER_2_SOURCES[domain]
            return info['score'], SourceTier.TIER_2_REPUTABLE.value, info['name']

        # Check Tier 3 (Social)
        if domain in cls.TIER_3_SOURCES:
            info = cls.TIER_3_SOURCES[domain]
            base_score = info['score']

            # Adjust for subreddit
            if domain == 'reddit.com' and subreddit:
                modifier = cls.SUBREDDIT_MODIFIERS.get(subreddit.lower(), 0.50)
                base_score = modifier
                info_name = f"Reddit (r/{subreddit})"
            else:
                info_name = info['name']

            return base_score, SourceTier.TIER_3_SOCIAL.value, info_name

        # Unknown
        return 0.3, SourceTier.TIER_4_UNKNOWN.value, domain


class AuthorCredibilityEvaluator:
    """Evaluates author credibility based on platform metrics"""

    @staticmethod
    def evaluate_reddit(
        author: str,
        score: Optional[int] = None,
        upvote_ratio: Optional[float] = None,
        total_comments: Optional[int] = None
    ) -> Tuple[float, Dict]:
        """Evaluate Reddit user credibility"""

        if author in ['AutoModerator', '[deleted]', '[removed]']:
            return 0.1, {'reason': 'Automated/deleted'}

        cred_score = 0.3  # Base
        factors = {}

        # Post engagement (0.0 to 0.3)
        if score is not None:
            if score >= 1000:
                engagement = 0.3
            elif score >= 500:
                engagement = 0.2
            elif score >= 100:
                engagement = 0.15
            elif score >= 50:
                engagement = 0.1
            else:
                engagement = 0.05

            cred_score += engagement
            factors['post_score'] = score
            factors['engagement_bonus'] = engagement

        # Upvote ratio (0.0 to 0.2)
        if upvote_ratio is not None:
            if upvote_ratio >= 0.95:
                ratio_bonus = 0.2
            elif upvote_ratio >= 0.90:
                ratio_bonus = 0.15
            elif upvote_ratio >= 0.80:
                ratio_bonus = 0.1
            elif upvote_ratio >= 0.70:
                ratio_bonus = 0.05
            else:
                ratio_bonus = 0.0

            cred_score += ratio_bonus
            factors['upvote_ratio'] = upvote_ratio
            factors['ratio_bonus'] = ratio_bonus

        # Comment engagement (0.0 to 0.2)
        if total_comments is not None:
            if total_comments >= 100:
                comment_bonus = 0.2
            elif total_comments >= 50:
                comment_bonus = 0.15
            elif total_comments >= 20:
                comment_bonus = 0.1
            else:
                comment_bonus = 0.05

            cred_score += comment_bonus
            factors['total_comments'] = total_comments
            factors['comment_bonus'] = comment_bonus

        # Cap at 0.8 for social media
        cred_score = min(cred_score, 0.8)

        return cred_score, factors

    @staticmethod
    def evaluate_journalist(source_tier: str) -> Tuple[float, Dict]:
        """Evaluate professional journalist"""
        if source_tier == SourceTier.TIER_1_PREMIUM.value:
            return 0.90, {'type': 'tier_1_journalist'}
        elif source_tier == SourceTier.TIER_2_REPUTABLE.value:
            return 0.80, {'type': 'tier_2_journalist'}
        else:
            return 0.50, {'type': 'unknown_journalist'}


class ContentQualityAnalyzer:
    """Analyzes content quality using heuristics"""

    @staticmethod
    def analyze(text: str, has_urls: bool = False) -> Dict[str, float]:
        """Fast heuristic-based content quality analysis"""
        scores = {}

        word_count = len(text.split()) if text else 0

        # Length quality (0.4 to 0.9)
        if 50 <= word_count <= 500:
            scores['length'] = 0.8
        elif 20 <= word_count < 50 or 500 < word_count <= 1000:
            scores['length'] = 0.6
        else:
            scores['length'] = 0.4

        # Citation presence (0.3 to 0.8)
        if has_urls:
            scores['citation'] = 0.8
        elif text and re.search(r'according to|report|study|analyst|source', text, re.I):
            scores['citation'] = 0.6
        else:
            scores['citation'] = 0.3

        # Specificity - numbers, dates, concrete data (0.4 to 0.8)
        has_numbers = bool(text and re.search(r'\d+\.?\d*%|\$\d+|Q[1-4]|FY\d{4}|\d{4}-\d{2}', text))
        scores['specificity'] = 0.7 if has_numbers else 0.4

        # Sensationalism check (penalty: -0.2 to 0.0)
        sensational = len(re.findall(
            r'\b(shocking|amazing|unbelievable|breaking|!!!|🚀🚀🚀)\b',
            text or '', re.I
        ))
        scores['sensationalism_penalty'] = -0.1 if sensational >= 2 else 0.0

        # Professional language (0.5 to 0.8)
        professional_terms = len(re.findall(
            r'\b(revenue|earnings|profit|quarter|fiscal|analyst|market|stock|company)\b',
            text or '', re.I
        ))
        scores['professionalism'] = 0.7 if professional_terms >= 3 else 0.5

        return scores


class CredibilityService:
    """
    Main credibility service with hybrid approach:
    - Heuristic scoring (source, author, content)
    - LLM analysis via Ollama for content credibility

    Default: Uses Ollama LLM for enhanced analysis
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        model_provider: str = "ollama",
        model_name: str = None,
        enable_llm: bool = True
    ):
        # Skip if already initialized (singleton)
        if CredibilityService._initialized:
            return

        logger.info("Initializing Credibility Service...")

        # Initialize evaluators
        self.source_evaluator = SourceCredibilityEvaluator()
        self.author_evaluator = AuthorCredibilityEvaluator()
        self.content_analyzer = ContentQualityAnalyzer()

        # Scoring weights
        self.SOURCE_WEIGHT = 0.35
        self.AUTHOR_WEIGHT = 0.25
        self.CONTENT_WEIGHT = 0.40  # Higher weight for LLM-enhanced content analysis

        # LLM configuration
        self.enable_llm = enable_llm
        self.llm = None
        self.parser = None
        self.model_provider = model_provider
        self.model_name = model_name or env_config.large_language_model or "llama3.2"

        if enable_llm:
            self._initialize_llm()

        CredibilityService._initialized = True
        logger.info(f"Credibility Service initialized (LLM: {self.enable_llm})")

    def _initialize_llm(self):
        """Initialize the LLM for content analysis"""
        try:
            self.llm: BaseChatModel = init_chat_model(
                model=self.model_name,
                model_provider=self.model_provider,
                temperature=0.1,
            )
            self.parser = JsonOutputParser()
            logger.info(f"LLM initialized: {self.model_provider}/{self.model_name}")
        except Exception as e:
            logger.warning(f"Failed to initialize LLM: {e}. Running with heuristics only.")
            self.enable_llm = False
            self.llm = None

    def _get_llm_credibility_prompt(self) -> ChatPromptTemplate:
        """Get the prompt template for LLM credibility analysis"""
        return ChatPromptTemplate.from_messages([
            (
                "system",
                """You are a financial news credibility analyst. Evaluate the credibility of financial content.

Consider:
1. Factual accuracy - Are claims verifiable? Are numbers/dates provided?
2. Source quality - Does it cite official sources (SEC, company filings)?
3. Language quality - Professional vs sensational/emotional language
4. Speculation vs fact - Is it opinion or based on data?
5. Potential bias or manipulation - Pump/dump signals, FOMO language

Output ONLY valid JSON, no additional text."""
            ),
            (
                "user",
                """Analyze this financial content for credibility:

Text: {text}
Source: {source}
Author: {author}

Return ONLY this JSON structure:
{{
    "content_credibility_score": <float 0.0-1.0>,
    "factual_accuracy": <float 0.0-1.0>,
    "language_quality": <float 0.0-1.0>,
    "is_speculative": <boolean>,
    "manipulation_risk": <"low"|"medium"|"high">,
    "reasoning": "<1-2 sentence explanation>",
    "red_flags": ["<flag1>", "<flag2>"] or []
}}"""
            )
        ])

    def _analyze_heuristic(self, item: Dict) -> Tuple[CredibilityScore, str, str, str]:
        """
        Analyze using heuristics only (fast).
        Returns: (CredibilityScore, text, domain, author)
        """
        warnings = []

        # Extract nested structures
        content = item.get('content', {})
        metadata = item.get('metadata', item)

        # Extract fields
        domain = (
            metadata.get('Domain', '') or
            item.get('Domain', '') or
            ''
        ).lower()

        subreddit = (
            metadata.get('Subreddit', '') or
            item.get('Subreddit', '') or
            item.get('subreddit', '') or
            ''
        )

        author = (
            metadata.get('Author', '') or
            item.get('Author', '') or
            item.get('author', '') or
            ''
        )

        # Extract text
        text = (
            content.get('clean_combined_withurl', '') or
            content.get('clean_combined_withouturl', '') or
            content.get('clean_combined', '') or
            content.get('clean_body', '') or
            item.get('clean_combined', '') or
            item.get('clean_body', '') or
            item.get('body', '') or
            ''
        )

        # Extract URLs
        urls = item.get('links', []) or item.get('urls', []) or []

        # Reddit metrics
        score = metadata.get('Score') or item.get('Score') or item.get('score')
        upvote_ratio = metadata.get('Upvote_Ratio') or item.get('Upvote_Ratio') or item.get('upvote_ratio')
        total_comments = metadata.get('Total_Comments') or item.get('Total_Comments') or item.get('num_comments')

        # Step 1: Source credibility
        source_score, source_tier, source_name = self.source_evaluator.evaluate(domain, subreddit)

        # Step 2: Author credibility
        if source_tier == SourceTier.TIER_3_SOCIAL.value and 'reddit' in domain:
            author_score, author_factors = self.author_evaluator.evaluate_reddit(
                author, score, upvote_ratio, total_comments
            )
        else:
            author_score, author_factors = self.author_evaluator.evaluate_journalist(source_tier)

        # Step 3: Content quality (heuristic)
        content_scores = self.content_analyzer.analyze(text, bool(urls))

        content_score = (
            content_scores['length'] * 0.25 +
            content_scores['citation'] * 0.25 +
            content_scores['specificity'] * 0.2 +
            content_scores['professionalism'] * 0.2 +
            content_scores['sensationalism_penalty'] * 0.1
        )

        # Overall score (will be updated if LLM is used)
        overall = (
            self.SOURCE_WEIGHT * source_score +
            self.AUTHOR_WEIGHT * author_score +
            self.CONTENT_WEIGHT * content_score
        )

        # Warnings
        if overall < 0.3:
            warnings.append("Very low credibility")
        elif overall < 0.5:
            warnings.append("Low credibility - verify independently")

        if source_tier == SourceTier.TIER_4_UNKNOWN.value:
            warnings.append("Unknown source")

        # Confidence
        confidence = 0.6 if not self.enable_llm else 0.5  # Lower without LLM confirmation
        if source_tier == SourceTier.TIER_1_PREMIUM.value:
            confidence = 0.95
        elif source_tier == SourceTier.TIER_2_REPUTABLE.value:
            confidence = 0.85

        cred_score = CredibilityScore(
            overall_score=round(overall, 4),
            source_score=round(source_score, 4),
            author_score=round(author_score, 4),
            content_score=round(content_score, 4),
            source_tier=source_tier,
            source_name=source_name,
            confidence=round(confidence, 4),
            warnings=warnings,
            details={
                'author_factors': author_factors,
                'content_quality': content_scores
            },
            llm_analysis=None
        )

        return cred_score, text, domain, author

    async def _analyze_with_llm(self, text: str, domain: str, author: str) -> Dict:
        """Analyze content credibility using LLM"""
        if not self.enable_llm or not self.llm or not text:
            return None

        prompt = self._get_llm_credibility_prompt()
        chain = prompt | self.llm | self.parser

        try:
            result = await chain.ainvoke({
                "text": text[:1500],  # Limit length
                "source": domain or "Unknown",
                "author": author or "Unknown"
            })
            return result
        except Exception as e:
            logger.error(f"LLM credibility analysis failed: {e}")
            return None

    def _analyze_with_llm_sync(self, text: str, domain: str, author: str) -> Dict:
        """Synchronous wrapper for LLM analysis"""
        if not self.enable_llm or not self.llm:
            return None

        try:
            return asyncio.run(self._analyze_with_llm(text, domain, author))
        except RuntimeError:
            # If already in async context, create new loop
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._analyze_with_llm(text, domain, author))
            finally:
                loop.close()

    def analyse(self, item: Dict) -> Dict:
        """
        Analyze a single item for credibility using hybrid approach.
        Combines heuristic scoring with LLM analysis.

        Returns the item enriched with credibility scores.
        """
        try:
            # Phase 1: Heuristic analysis
            cred, text, domain, author = self._analyze_heuristic(item)

            # Phase 2: LLM analysis (if enabled)
            llm_result = None
            if self.enable_llm and self.llm:
                llm_result = self._analyze_with_llm_sync(text, domain, author)

                if llm_result:
                    # Blend heuristic and LLM scores
                    llm_content_score = llm_result.get('content_credibility_score', cred.content_score)

                    # Weighted blend: 40% heuristic + 60% LLM for content
                    blended_content_score = (
                        0.4 * cred.content_score +
                        0.6 * llm_content_score
                    )

                    # Recalculate overall with blended content
                    blended_overall = (
                        self.SOURCE_WEIGHT * cred.source_score +
                        self.AUTHOR_WEIGHT * cred.author_score +
                        self.CONTENT_WEIGHT * blended_content_score
                    )

                    # Update scores
                    cred = CredibilityScore(
                        overall_score=round(blended_overall, 4),
                        source_score=cred.source_score,
                        author_score=cred.author_score,
                        content_score=round(blended_content_score, 4),
                        source_tier=cred.source_tier,
                        source_name=cred.source_name,
                        confidence=0.85,  # Higher confidence with LLM
                        warnings=cred.warnings + (llm_result.get('red_flags', []) or []),
                        details=cred.details,
                        llm_analysis=llm_result
                    )

            # Enrich item with credibility data
            item['credibility_score'] = cred.overall_score
            item['source_credibility'] = cred.source_score
            item['author_credibility'] = cred.author_score
            item['content_credibility'] = cred.content_score
            item['source_tier'] = cred.source_tier
            item['source_name'] = cred.source_name
            item['credibility_confidence'] = cred.confidence
            item['credibility_warnings'] = cred.warnings
            item['credibility_details'] = cred.details

            if llm_result:
                item['llm_credibility_analysis'] = llm_result

            return item

        except Exception as e:
            logger.error(f"Credibility analysis failed: {e}")
            item['credibility_score'] = 0.5
            item['source_credibility'] = 0.5
            item['author_credibility'] = 0.5
            item['content_credibility'] = 0.5
            item['source_tier'] = SourceTier.TIER_4_UNKNOWN.value
            item['credibility_warnings'] = [f"Analysis error: {str(e)}"]
            return item

    async def analyse_async(self, item: Dict) -> Dict:
        """Async version of analyse for batch processing"""
        try:
            cred, text, domain, author = self._analyze_heuristic(item)

            llm_result = None
            if self.enable_llm and self.llm:
                llm_result = await self._analyze_with_llm(text, domain, author)

                if llm_result:
                    llm_content_score = llm_result.get('content_credibility_score', cred.content_score)
                    blended_content_score = 0.4 * cred.content_score + 0.6 * llm_content_score
                    blended_overall = (
                        self.SOURCE_WEIGHT * cred.source_score +
                        self.AUTHOR_WEIGHT * cred.author_score +
                        self.CONTENT_WEIGHT * blended_content_score
                    )

                    cred = CredibilityScore(
                        overall_score=round(blended_overall, 4),
                        source_score=cred.source_score,
                        author_score=cred.author_score,
                        content_score=round(blended_content_score, 4),
                        source_tier=cred.source_tier,
                        source_name=cred.source_name,
                        confidence=0.85,
                        warnings=cred.warnings + (llm_result.get('red_flags', []) or []),
                        details=cred.details,
                        llm_analysis=llm_result
                    )

            item['credibility_score'] = cred.overall_score
            item['source_credibility'] = cred.source_score
            item['author_credibility'] = cred.author_score
            item['content_credibility'] = cred.content_score
            item['source_tier'] = cred.source_tier
            item['source_name'] = cred.source_name
            item['credibility_confidence'] = cred.confidence
            item['credibility_warnings'] = cred.warnings
            item['credibility_details'] = cred.details

            if llm_result:
                item['llm_credibility_analysis'] = llm_result

            return item

        except Exception as e:
            logger.error(f"Async credibility analysis failed: {e}")
            item['credibility_score'] = 0.5
            item['source_tier'] = SourceTier.TIER_4_UNKNOWN.value
            item['credibility_warnings'] = [f"Analysis error: {str(e)}"]
            return item

    async def process_data(
        self,
        data: List[Dict],
        batch_size: int = 5
    ) -> List[Dict]:
        """
        Process multiple items with async LLM analysis.
        """
        logger.info(f"Processing {len(data)} items for credibility analysis")

        results = []

        # Process in batches for LLM efficiency
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]

            if self.enable_llm:
                # Async batch processing
                tasks = [self.analyse_async(item) for item in batch]
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)
            else:
                # Sync processing without LLM
                for item in batch:
                    results.append(self.analyse(item))

        logger.info(f"Completed credibility analysis for {len(results)} items")
        return results


# Create singleton instance (LLM enabled by default with Ollama)
credibility_service = CredibilityService()


# Main for testing
async def main():
    print("="*80)
    print("CREDIBILITY SERVICE TEST (Hybrid: Heuristic + Ollama LLM)")
    print("="*80)

    test_data = [
        {
            "Post_ID": "test1",
            "Domain": "reuters.com",
            "Author": "Jane Doe",
            "clean_combined": "Apple Inc reported Q4 earnings of $1.50 per share, beating analyst expectations. Revenue reached $89.5 billion, up 8% YoY.",
            "urls": ["https://reuters.com/tech/apple"],
            "Score": 250,
            "Upvote_Ratio": 0.95
        },
        {
            "Post_ID": "test2",
            "Domain": "reddit.com",
            "Subreddit": "wallstreetbets",
            "Author": "DiamondHands420",
            "clean_combined": "TSLA to the moon!!! 🚀🚀🚀 Trust me bro, this is gonna 10x!!!",
            "urls": [],
            "Score": 5,
            "Upvote_Ratio": 0.55,
            "Total_Comments": 3
        },
        {
            "Post_ID": "test3",
            "Domain": "reddit.com",
            "Subreddit": "investing",
            "Author": "ValueInvestor99",
            "clean_combined": "Analysis of Microsoft's cloud revenue growth based on latest quarterly report. Azure grew 30% YoY according to their earnings call.",
            "urls": ["https://microsoft.com/investor"],
            "Score": 450,
            "Upvote_Ratio": 0.92,
            "Total_Comments": 67
        }
    ]

    # Test with LLM
    print("\nTesting with Ollama LLM...\n")

    results = await credibility_service.process_data(test_data)

    for item in results:
        print(f"Post ID: {item['Post_ID']}")
        print(f"Source: {item.get('Domain')} ({item.get('Subreddit', 'N/A')})")
        print(f"Overall Score: {item['credibility_score']:.3f}")
        print(f"  - Source: {item['source_credibility']:.3f}")
        print(f"  - Author: {item['author_credibility']:.3f}")
        print(f"  - Content: {item['content_credibility']:.3f}")
        print(f"Tier: {item['source_tier']}")
        print(f"Confidence: {item['credibility_confidence']:.3f}")

        if item.get('llm_credibility_analysis'):
            llm = item['llm_credibility_analysis']
            print(f"LLM Analysis:")
            print(f"  - Reasoning: {llm.get('reasoning', 'N/A')}")
            print(f"  - Manipulation Risk: {llm.get('manipulation_risk', 'N/A')}")
            if llm.get('red_flags'):
                print(f"  - Red Flags: {llm['red_flags']}")

        if item['credibility_warnings']:
            print(f"Warnings: {', '.join(item['credibility_warnings'])}")
        print("-"*80)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
