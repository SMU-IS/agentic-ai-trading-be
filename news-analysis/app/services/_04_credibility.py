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
    """Analyzes content quality without requiring LLM"""
    
    @staticmethod
    def analyze(text: str, has_urls: bool = False) -> Dict[str, float]:
        """Fast heuristic-based content quality analysis"""
        scores = {}
        
        word_count = len(text.split())
        
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
        elif re.search(r'according to|report|study|analyst|source', text, re.I):
            scores['citation'] = 0.6
        else:
            scores['citation'] = 0.3
        
        # Specificity - numbers, dates, concrete data (0.4 to 0.8)
        has_numbers = bool(re.search(r'\d+\.?\d*%|\$\d+|Q[1-4]|FY\d{4}|\d{4}-\d{2}', text))
        scores['specificity'] = 0.7 if has_numbers else 0.4
        
        # Sensationalism check (penalty: -0.2 to 0.0)
        sensational = len(re.findall(
            r'\b(shocking|amazing|unbelievable|breaking|!!!|🚀🚀🚀)\b',
            text, re.I
        ))
        scores['sensationalism_penalty'] = -0.1 if sensational >= 2 else 0.0
        
        # Professional language (0.5 to 0.8)
        professional_terms = len(re.findall(
            r'\b(revenue|earnings|profit|quarter|fiscal|analyst|market|stock|company)\b',
            text, re.I
        ))
        scores['professionalism'] = 0.7 if professional_terms >= 3 else 0.5
        
        return scores


class CredibilityService:
    """
    Main credibility service with hybrid approach:
    - Fast heuristic scoring for all items
    - Optional async LLM fact-checking for high-value items
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(
        self,
        model_provider: str = "google_genai",
        model_name: str = None,
        enable_llm: bool = False
    ):
        if self._initialized:
            return
        
        logger.info("Initializing Credibility Service...")
        
        # Initialize evaluators
        self.source_evaluator = SourceCredibilityEvaluator()
        self.author_evaluator = AuthorCredibilityEvaluator()
        self.content_analyzer = ContentQualityAnalyzer()
        
        # Scoring weights
        self.SOURCE_WEIGHT = 0.40
        self.AUTHOR_WEIGHT = 0.30
        self.CONTENT_WEIGHT = 0.30
        
        # LLM configuration
        self.enable_llm = enable_llm
        self.llm = None
        self.parser = None
        
        if enable_llm:
            try:
                model_name = model_name or env_config.large_language_model
                self.llm: BaseChatModel = init_chat_model(
                    model=model_name,
                    model_provider=model_provider,
                    temperature=0,
                )
                self.parser = JsonOutputParser()
                logger.info(f"LLM fact-checking enabled: {model_provider}/{model_name}")
            except Exception as e:
                logger.warning(f"Failed to initialize LLM: {e}. Running without fact-checking.")
                self.enable_llm = False
        
        self._initialized = True
        logger.info("Credibility Service initialized")
    
    def _analyze_single(self, item: Dict) -> CredibilityScore:
        """
        Analyze single item without LLM (fast)
        """
        warnings = []
        
        # Extract fields
        domain = item.get('Domain', '').lower()
        subreddit = item.get('Subreddit', '')
        author = item.get('Author', '')
        text = item.get('clean_combined', '') or item.get('clean_body', '')
        urls = item.get('urls', [])
        
        # Reddit metrics
        score = item.get('Score', None)
        upvote_ratio = item.get('Upvote_Ratio', None)
        total_comments = item.get('Total_Comments', None)
        
        # Step 1: Source credibility
        source_score, source_tier, source_name = self.source_evaluator.evaluate(
            domain, subreddit
        )
        
        # Step 2: Author credibility
        if source_tier == SourceTier.TIER_3_SOCIAL.value and 'reddit' in domain:
            author_score, author_factors = self.author_evaluator.evaluate_reddit(
                author, score, upvote_ratio, total_comments
            )
        else:
            author_score, author_factors = self.author_evaluator.evaluate_journalist(
                source_tier
            )
        
        # Step 3: Content quality (heuristic)
        content_scores = self.content_analyzer.analyze(text, bool(urls))
        
        # Weighted content score
        content_score = (
            content_scores['length'] * 0.25 +
            content_scores['citation'] * 0.25 +
            content_scores['specificity'] * 0.2 +
            content_scores['professionalism'] * 0.2 +
            content_scores['sensationalism_penalty'] * 0.1
        )
        
        # Step 4: Overall score
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
        
        # Confidence in assessment
        confidence = 0.7  # Base confidence without LLM
        if source_tier == SourceTier.TIER_1_PREMIUM.value:
            confidence = 0.95
        elif source_tier == SourceTier.TIER_2_REPUTABLE.value:
            confidence = 0.85
        
        return CredibilityScore(
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
            }
        )
    
    async def _fact_check_with_llm(self, text: str) -> Dict:
        """Async LLM fact-checking for high-value items"""
        if not self.enable_llm or not self.llm:
            return {
                'factual_accuracy_score': 0.5,
                'is_speculative': False,
                'reasoning': 'LLM disabled'
            }
        
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a financial fact-checker. Analyze text for credibility. Output ONLY valid JSON."
            ),
            (
                "user",
                """Analyze this financial news for credibility:

Text: {text}

Evaluate:
1. Factual accuracy (0.0 to 1.0)
2. Is it speculative vs factual?
3. Brief reasoning

Return ONLY JSON:
{{
    "factual_accuracy_score": <float 0.0-1.0>,
    "is_speculative": <boolean>,
    "reasoning": "<brief explanation>"
}}"""
            )
        ])
        
        chain = prompt | self.llm | self.parser
        
        try:
            result = await chain.ainvoke({"text": text[:1000]})  # Limit length
            return result
        except Exception as e:
            logger.error(f"LLM fact-check failed: {e}")
            return {
                'factual_accuracy_score': 0.5,
                'is_speculative': True,
                'reasoning': f'Error: {str(e)[:50]}'
            }
    
    async def process_data(
        self,
        data: List[Dict],
        enable_fact_check: bool = False,
        fact_check_threshold: int = 100,
        batch_size: int = 5
    ) -> List[Dict]:
        """
        Process items with optional async LLM fact-checking
        
        Args:
            data: List of items to process
            enable_fact_check: Enable LLM fact-checking
            fact_check_threshold: Only fact-check posts with score > threshold
            batch_size: Batch size for LLM calls
        """
        logger.info(f"Processing {len(data)} items for credibility analysis")
        
        results = []
        
        # Phase 1: Fast heuristic analysis for all items
        for item in data:
            try:
                cred = self._analyze_single(item)
                
                # Add to item
                item['credibility_score'] = cred.overall_score
                item['source_credibility'] = cred.source_score
                item['author_credibility'] = cred.author_score
                item['content_credibility'] = cred.content_score
                item['source_tier'] = cred.source_tier
                item['credibility_confidence'] = cred.confidence
                item['credibility_warnings'] = cred.warnings
                
                # Store for potential fact-checking
                item['_temp_cred_obj'] = cred
                results.append(item)
                
            except Exception as e:
                logger.error(f"Credibility analysis failed for {item.get('Post_ID')}: {e}")
                item['credibility_score'] = 0.5
                item['source_credibility'] = 0.5
                item['author_credibility'] = 0.5
                item['content_credibility'] = 0.5
                item['source_tier'] = SourceTier.TIER_4_UNKNOWN.value
                item['credibility_warnings'] = [f"Analysis error: {str(e)}"]
                results.append(item)
        
        # Phase 2: Optional LLM fact-checking for high-value items
        if enable_fact_check and self.enable_llm:
            # Filter items for fact-checking
            items_to_check = [
                item for item in results
                if item.get('Score', 0) > fact_check_threshold
                and item.get('_temp_cred_obj')
            ]
            
            logger.info(f"Fact-checking {len(items_to_check)} high-value items")
            
            # Process in batches
            for i in range(0, len(items_to_check), batch_size):
                batch = items_to_check[i:i + batch_size]
                
                # Prepare batch inputs
                batch_texts = [
                    item.get('clean_combined', '')[:1000]
                    for item in batch
                ]
                
                # Async fact-check
                try:
                    fact_check_tasks = [
                        self._fact_check_with_llm(text)
                        for text in batch_texts
                    ]
                    llm_results = await asyncio.gather(*fact_check_tasks)
                    
                    # Update scores with LLM results
                    for item, llm_res in zip(batch, llm_results):
                        original_cred = item['_temp_cred_obj']
                        
                        # Blend: 70% heuristic + 30% LLM
                        enhanced_content_score = (
                            0.7 * original_cred.content_score +
                            0.3 * llm_res.get('factual_accuracy_score', 0.5)
                        )
                        
                        # Recalculate overall
                        enhanced_overall = (
                            self.SOURCE_WEIGHT * original_cred.source_score +
                            self.AUTHOR_WEIGHT * original_cred.author_score +
                            self.CONTENT_WEIGHT * enhanced_content_score
                        )
                        
                        # Update
                        item['content_credibility'] = round(enhanced_content_score, 4)
                        item['credibility_score'] = round(enhanced_overall, 4)
                        item['credibility_confidence'] = 0.9  # Higher with LLM
                        item['credibility_metadata'] = llm_res
                        
                except Exception as e:
                    logger.error(f"Batch fact-check failed: {e}")
        
        # Cleanup temp objects
        for item in results:
            item.pop('_temp_cred_obj', None)
        
        logger.info(f"Completed credibility analysis for {len(results)} items")
        return results


# Singleton instance
credibility_service = CredibilityService()


# Main for testing
async def main():
    print("="*80)
    print("CREDIBILITY SERVICE TEST")
    print("="*80)
    
    # Test data
    test_data = [
        {
            "Post_ID": "test1",
            "Domain": "reuters.com",
            "Author": "Jane Doe",
            "clean_combined": "Apple Inc reported Q4 earnings of $1.50 per share, beating analyst expectations.",
            "urls": ["https://reuters.com/tech/apple"],
            "Score": 250,
            "Upvote_Ratio": 0.95
        },
        {
            "Post_ID": "test2",
            "Domain": "reddit.com",
            "Subreddit": "wallstreetbets",
            "Author": "DiamondHands420",
            "clean_combined": "TSLA to the moon!!! 🚀🚀🚀 Trust me bro",
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
            "clean_combined": "Analysis of Microsoft's cloud revenue growth based on latest quarterly report. Azure grew 30% YoY.",
            "urls": ["https://microsoft.com/investor"],
            "Score": 450,
            "Upvote_Ratio": 0.92,
            "Total_Comments": 67
        }
    ]
    
    # Initialize service
    service = CredibilityService(enable_llm=False)
    
    # Process without LLM
    results = await service.process_data(test_data, enable_fact_check=False)
    
    print("\nRESULTS (Heuristic Only):\n")
    for item in results:
        print(f"Post ID: {item['Post_ID']}")
        print(f"Source: {item.get('Domain')} ({item.get('Subreddit', 'N/A')})")
        print(f"Overall Score: {item['credibility_score']:.3f}")
        print(f"  - Source: {item['source_credibility']:.3f}")
        print(f"  - Author: {item['author_credibility']:.3f}")
        print(f"  - Content: {item['content_credibility']:.3f}")
        print(f"Tier: {item['source_tier']}")
        print(f"Confidence: {item['credibility_confidence']:.3f}")
        if item['credibility_warnings']:
            print(f"Warnings: {', '.join(item['credibility_warnings'])}")
        print("-"*80)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())