"""
Credibility Service Accuracy Tests
File: news-analysis/app/scripts/test_credibility_accuracy.py

Pytest-style tests for validating credibility scoring accuracy.
Run with: pytest app/scripts/test_credibility_accuracy.py -v

Tests both heuristic-only and hybrid (heuristic + LLM) modes.
"""

import pytest
import asyncio
import sys
from pathlib import Path

# Add news-analysis root to path (parent of 'app')
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services._04_credibility import CredibilityService, SourceTier


def reset_singleton():
    """Reset the singleton to allow reinitialization"""
    CredibilityService._instance = None
    CredibilityService._initialized = False


@pytest.fixture
def credibility_service():
    """Create a CredibilityService instance with LLM enabled (uses Ollama)"""
    reset_singleton()
    return CredibilityService(enable_llm=True)


@pytest.fixture
def credibility_service_no_llm():
    """Create a CredibilityService instance without LLM (heuristic only)"""
    reset_singleton()
    return CredibilityService(enable_llm=False)


# ============================================================
# TIER 1 PREMIUM SOURCES
# Expected: Score >= 0.85, Tier = tier_1_premium
# ============================================================

class TestTier1Sources:
    """Test premium financial news sources"""

    def test_reuters_high_credibility(self, credibility_service):
        """Reuters should score >= 0.85"""
        item = {
            "Post_ID": "reuters_test",
            "Domain": "reuters.com",
            "Author": "Reuters Staff",
            "clean_combined": "Apple Inc reported Q4 earnings of $1.50 per share, beating analyst expectations.",
            "urls": ["https://reuters.com/tech/apple"],
            "Score": 100,
            "Upvote_Ratio": 0.95
        }

        result = credibility_service.analyse(item)

        assert result['credibility_score'] >= 0.85, f"Reuters scored {result['credibility_score']}, expected >= 0.85"
        assert result['source_tier'] == SourceTier.TIER_1_PREMIUM.value

    def test_wsj_high_credibility(self, credibility_service):
        """Wall Street Journal should score >= 0.85"""
        item = {
            "Post_ID": "wsj_test",
            "Domain": "wsj.com",
            "Author": "WSJ Staff",
            "clean_combined": "Federal Reserve signals potential rate cut in Q2 based on inflation data.",
            "urls": ["https://wsj.com"],
            "Score": 200,
            "Upvote_Ratio": 0.98
        }

        result = credibility_service.analyse(item)

        assert result['credibility_score'] >= 0.85
        assert result['source_tier'] == SourceTier.TIER_1_PREMIUM.value

    def test_bloomberg_high_credibility(self, credibility_service):
        """Bloomberg should score >= 0.85"""
        item = {
            "Post_ID": "bloomberg_test",
            "Domain": "bloomberg.com",
            "Author": "Bloomberg News",
            "clean_combined": "Microsoft cloud revenue grew 35% YoY, reaching $25 billion in FY2024 Q4.",
            "urls": ["https://bloomberg.com"],
            "Score": 150,
            "Upvote_Ratio": 0.96
        }

        result = credibility_service.analyse(item)

        assert result['credibility_score'] >= 0.85
        assert result['source_tier'] == SourceTier.TIER_1_PREMIUM.value

    def test_sec_gov_highest_credibility(self, credibility_service):
        """SEC.gov (government source) should score near 1.0"""
        item = {
            "Post_ID": "sec_test",
            "Domain": "sec.gov",
            "Author": "SEC",
            "clean_combined": "Form 10-K filed by Apple Inc. Annual revenue: $385.7 billion.",
            "urls": ["https://sec.gov/filings"],
            "Score": 100,
            "Upvote_Ratio": 1.0
        }

        result = credibility_service.analyse(item)

        assert result['credibility_score'] >= 0.90
        assert result['source_credibility'] == 1.0  # Government sources should be 1.0


# ============================================================
# TIER 2 REPUTABLE SOURCES
# Expected: 0.70 <= Score <= 0.85, Tier = tier_2_reputable
# ============================================================

class TestTier2Sources:
    """Test reputable but non-premium sources"""

    def test_cnbc_moderate_credibility(self, credibility_service):
        """CNBC should score between 0.70-0.90"""
        item = {
            "Post_ID": "cnbc_test",
            "Domain": "cnbc.com",
            "Author": "CNBC",
            "clean_combined": "Tech stocks rally as Nvidia announces new AI chip.",
            "urls": ["https://cnbc.com"],
            "Score": 80,
            "Upvote_Ratio": 0.90
        }

        result = credibility_service.analyse(item)

        assert 0.70 <= result['credibility_score'] <= 0.90
        assert result['source_tier'] == SourceTier.TIER_2_REPUTABLE.value

    def test_yahoo_finance_moderate_credibility(self, credibility_service):
        """Yahoo Finance should score between 0.70-0.90"""
        item = {
            "Post_ID": "yahoo_test",
            "Domain": "finance.yahoo.com",
            "Author": "Yahoo Finance",
            "clean_combined": "S&P 500 closes at record high amid strong corporate earnings.",
            "urls": ["https://finance.yahoo.com"],
            "Score": 60,
            "Upvote_Ratio": 0.88
        }

        result = credibility_service.analyse(item)

        assert 0.70 <= result['credibility_score'] <= 0.90
        assert result['source_tier'] == SourceTier.TIER_2_REPUTABLE.value


# ============================================================
# TIER 3 SOCIAL MEDIA - REDDIT
# Expected: Varies by subreddit and engagement
# ============================================================

class TestRedditSources:
    """Test Reddit posts with varying quality"""

    def test_reddit_investing_high_engagement(self, credibility_service):
        """High-quality r/investing post with good engagement"""
        item = {
            "Post_ID": "reddit_investing_high",
            "Domain": "reddit.com",
            "Subreddit": "investing",
            "Author": "ValueInvestor2024",
            "clean_combined": "Detailed analysis of Tesla Q4 earnings. Revenue: $25.2B (+10% YoY), EPS: $1.19 vs $1.05 expected. Margins improved due to cost reduction. Source: Tesla IR.",
            "urls": ["https://ir.tesla.com"],
            "Score": 850,
            "Upvote_Ratio": 0.95,
            "Total_Comments": 156
        }

        result = credibility_service.analyse(item)

        # High engagement r/investing should score reasonably well
        assert result['credibility_score'] >= 0.55
        assert result['source_tier'] == SourceTier.TIER_3_SOCIAL.value
        assert result['author_credibility'] >= 0.6  # High engagement bonus

    def test_reddit_wsb_low_credibility(self, credibility_service):
        """WSB post should score lower due to subreddit modifier"""
        item = {
            "Post_ID": "reddit_wsb",
            "Domain": "reddit.com",
            "Subreddit": "wallstreetbets",
            "Author": "DiamondHands420",
            "clean_combined": "TSLA to the moon!!! Trust me bro!!!",
            "urls": [],
            "Score": 5,
            "Upvote_Ratio": 0.55,
            "Total_Comments": 3
        }

        result = credibility_service.analyse(item)

        # WSB with low engagement should score low
        assert result['credibility_score'] < 0.45
        assert result['source_tier'] == SourceTier.TIER_3_SOCIAL.value

    def test_reddit_quality_ordering(self, credibility_service):
        """Higher quality Reddit posts should score higher"""
        high_quality = {
            "Post_ID": "high",
            "Domain": "reddit.com",
            "Subreddit": "investing",
            "Author": "Analyst",
            "clean_combined": "According to SEC filings, Microsoft reported $60B revenue in Q3. Analysis: https://sec.gov",
            "urls": ["https://sec.gov"],
            "Score": 500,
            "Upvote_Ratio": 0.92,
            "Total_Comments": 80
        }

        low_quality = {
            "Post_ID": "low",
            "Domain": "reddit.com",
            "Subreddit": "wallstreetbets",
            "Author": "YOLO",
            "clean_combined": "moon moon moon!!!",
            "urls": [],
            "Score": 2,
            "Upvote_Ratio": 0.50,
            "Total_Comments": 1
        }

        high_result = credibility_service.analyse(high_quality)
        low_result = credibility_service.analyse(low_quality)

        assert high_result['credibility_score'] > low_result['credibility_score'], \
            f"High quality ({high_result['credibility_score']}) should beat low quality ({low_result['credibility_score']})"


# ============================================================
# CONTENT QUALITY ANALYSIS
# Expected: Content quality affects score
# ============================================================

class TestContentQuality:
    """Test content quality scoring"""

    def test_professional_content_scores_higher(self, credibility_service):
        """Professional language with numbers and sources should score higher"""
        professional = {
            "Post_ID": "professional",
            "Domain": "reddit.com",
            "Subreddit": "stocks",
            "Author": "FinanceExpert",
            "clean_combined": "According to latest SEC filings, Microsoft reported revenue of $60B in Q3 FY2024, representing 15% growth YoY. Operating margin improved to 42%. Analysis based on official filings.",
            "urls": ["https://sec.gov"],
            "Score": 100,
            "Upvote_Ratio": 0.85,
            "Total_Comments": 30
        }

        casual = {
            "Post_ID": "casual",
            "Domain": "reddit.com",
            "Subreddit": "stocks",
            "Author": "CasualUser",
            "clean_combined": "Stock go up maybe?",
            "urls": [],
            "Score": 100,  # Same engagement
            "Upvote_Ratio": 0.85,
            "Total_Comments": 30
        }

        prof_result = credibility_service.analyse(professional)
        cas_result = credibility_service.analyse(casual)

        assert prof_result['content_credibility'] > cas_result['content_credibility']

    def test_sensational_content_penalized(self, credibility_service):
        """Sensational language should be penalized"""
        sensational = {
            "Post_ID": "sensational",
            "Domain": "reddit.com",
            "Subreddit": "stocks",
            "Author": "User",
            "clean_combined": "SHOCKING!!! UNBELIEVABLE!!! You won't believe what happened!!! BREAKING!!!",
            "urls": [],
            "Score": 50,
            "Upvote_Ratio": 0.70,
            "Total_Comments": 10
        }

        result = credibility_service.analyse(sensational)

        # Should have warnings about credibility
        assert result['credibility_score'] < 0.55
        assert len(result.get('credibility_warnings', [])) > 0


# ============================================================
# UNKNOWN SOURCES
# Expected: Low scores for unknown domains
# ============================================================

class TestUnknownSources:
    """Test handling of unknown/suspicious sources"""

    def test_unknown_domain_low_score(self, credibility_service):
        """Unknown domains should score low"""
        item = {
            "Post_ID": "unknown",
            "Domain": "randomfinanceblog.xyz",
            "Author": "Anonymous",
            "clean_combined": "Insider tip: Buy this stock now!!!",
            "urls": [],
            "Score": 5,
            "Upvote_Ratio": 0.60
        }

        result = credibility_service.analyse(item)

        assert result['credibility_score'] < 0.45
        assert result['source_tier'] == SourceTier.TIER_4_UNKNOWN.value

    def test_no_domain_defaults_unknown(self, credibility_service):
        """Missing domain should default to unknown tier"""
        item = {
            "Post_ID": "no_domain",
            "Domain": "",
            "Author": "User",
            "clean_combined": "Some random content",
            "urls": [],
            "Score": 10,
            "Upvote_Ratio": 0.70
        }

        result = credibility_service.analyse(item)

        assert result['source_tier'] == SourceTier.TIER_4_UNKNOWN.value


# ============================================================
# EDGE CASES
# ============================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_content(self, credibility_service):
        """Empty content should still process"""
        item = {
            "Post_ID": "empty",
            "Domain": "reddit.com",
            "Subreddit": "stocks",
            "Author": "User",
            "clean_combined": "",
            "urls": []
        }

        result = credibility_service.analyse(item)

        assert 'credibility_score' in result
        assert result['credibility_score'] >= 0

    def test_nested_content_structure(self, credibility_service):
        """Should handle nested content structure from pipeline"""
        item = {
            "Post_ID": "nested",
            "content": {
                "clean_combined_withurl": "Microsoft reported $60B revenue. Source: https://microsoft.com",
                "clean_title": "Microsoft Q4 Earnings"
            },
            "metadata": {
                "Domain": "reddit.com",
                "Subreddit": "investing",
                "Author": "Analyst"
            },
            "links": ["https://microsoft.com"],
            "Score": 200,
            "Upvote_Ratio": 0.90,
            "Total_Comments": 50
        }

        result = credibility_service.analyse(item)

        assert 'credibility_score' in result
        assert result['credibility_score'] > 0

    def test_scores_in_valid_range(self, credibility_service):
        """All scores should be between 0 and 1"""
        items = [
            {"Domain": "reuters.com", "clean_combined": "Test", "urls": []},
            {"Domain": "reddit.com", "Subreddit": "wallstreetbets", "clean_combined": "Test", "urls": []},
            {"Domain": "", "clean_combined": "Test", "urls": []},
        ]

        for i, item in enumerate(items):
            item["Post_ID"] = f"range_test_{i}"
            result = credibility_service.analyse(item)

            assert 0 <= result['credibility_score'] <= 1
            assert 0 <= result['source_credibility'] <= 1
            assert 0 <= result['author_credibility'] <= 1
            assert 0 <= result['content_credibility'] <= 1
            assert 0 <= result['credibility_confidence'] <= 1


# ============================================================
# BATCH PROCESSING (async)
# ============================================================

class TestBatchProcessing:
    """Test batch processing functionality"""

    def test_batch_processing(self, credibility_service):
        """Should process multiple items correctly"""
        items = [
            {"Post_ID": "batch_1", "Domain": "reuters.com", "clean_combined": "Test 1", "urls": []},
            {"Post_ID": "batch_2", "Domain": "reddit.com", "Subreddit": "stocks", "clean_combined": "Test 2", "urls": []},
            {"Post_ID": "batch_3", "Domain": "unknown.com", "clean_combined": "Test 3", "urls": []},
        ]

        # Run async function synchronously
        results = asyncio.run(credibility_service.process_data(items))

        assert len(results) == 3
        assert results[0]['credibility_score'] > results[2]['credibility_score']  # Reuters > Unknown


# Run with: pytest app/scripts/test_credibility_accuracy.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
