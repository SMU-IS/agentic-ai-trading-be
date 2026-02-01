import asyncio
import json
import logging
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services._04_credibility import credibility_service, CredibilityService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def print_header(title: str):
    """Print formatted header"""
    print("\n" + "="*100)
    print(f"  {title}")
    print("="*100 + "\n")


def print_result(item: dict):
    """Print formatted credibility result"""
    print(f"{'Post ID:':<20} {item.get('Post_ID', 'N/A')}")
    print(f"{'Source:':<20} {item.get('Domain', 'N/A')}")
    if item.get('Subreddit'):
        print(f"{'Subreddit:':<20} r/{item['Subreddit']}")
    print(f"{'Author:':<20} {item.get('Author', 'N/A')}")
    
    # Scores
    overall = item.get('credibility_score', 0)
    color = "\033[92m" if overall >= 0.7 else "\033[93m" if overall >= 0.5 else "\033[91m"
    reset = "\033[0m"
    
    print(f"\n{'Overall Score:':<20} {color}{overall:.4f}{reset}")
    print(f"{'  Source:':<20} {item.get('source_credibility', 0):.4f}")
    print(f"{'  Author:':<20} {item.get('author_credibility', 0):.4f}")
    print(f"{'  Content:':<20} {item.get('content_credibility', 0):.4f}")
    print(f"{'Tier:':<20} {item.get('source_tier', 'N/A')}")
    print(f"{'Confidence:':<20} {item.get('credibility_confidence', 0):.4f}")
    
    if item.get('credibility_warnings'):
        print(f"{'Warnings:':<20} {', '.join(item['credibility_warnings'])}")
    
    print("-"*100)


async def test_tier_1_sources():
    """Test Tier 1 premium sources"""
    print_header("TEST 1: Tier 1 Premium Sources (Should Score 0.85+)")
    
    test_data = [
        {
            "Post_ID": "tier1_reuters",
            "Domain": "reuters.com",
            "Author": "Reuters Staff",
            "clean_combined": "Apple Inc (AAPL.O) reported quarterly revenue of $90 billion, beating analyst expectations of $88 billion.",
            "urls": ["https://reuters.com"],
            "Score": 100,
            "Upvote_Ratio": 0.95
        },
        {
            "Post_ID": "tier1_wsj",
            "Domain": "wsj.com",
            "Author": "Wall Street Journal",
            "clean_combined": "Federal Reserve signals potential rate cut in Q2 2025 based on inflation data.",
            "urls": ["https://wsj.com"],
            "Score": 200,
            "Upvote_Ratio": 0.98
        },
        {
            "Post_ID": "tier1_ft",
            "Domain": "ft.com",
            "Author": "Financial Times",
            "clean_combined": "Microsoft cloud revenue grew 35% YoY in FY2024 Q4, reaching $25 billion.",
            "urls": ["https://ft.com"],
            "Score": 150,
            "Upvote_Ratio": 0.96
        }
    ]
    
    service = CredibilityService()
    results = await service.process_data(test_data)
    
    for item in results:
        print_result(item)
    
    # Validate
    passed = all(item['credibility_score'] >= 0.85 for item in results)
    print(f"\n{'✅ PASS' if passed else '❌ FAIL'}: All Tier 1 sources scored 0.85+\n")
    
    return results


async def test_tier_2_sources():
    """Test Tier 2 reputable sources"""
    print_header("TEST 2: Tier 2 Reputable Sources (Should Score 0.70-0.85)")
    
    test_data = [
        {
            "Post_ID": "tier2_cnbc",
            "Domain": "cnbc.com",
            "Author": "CNBC Staff",
            "clean_combined": "Tech stocks rally as Nvidia announces new AI chip.",
            "urls": ["https://cnbc.com"],
            "Score": 80,
            "Upvote_Ratio": 0.90
        },
        {
            "Post_ID": "tier2_yahoo",
            "Domain": "finance.yahoo.com",
            "Author": "Yahoo Finance",
            "clean_combined": "S&P 500 closes at record high amid strong corporate earnings.",
            "urls": ["https://finance.yahoo.com"],
            "Score": 60,
            "Upvote_Ratio": 0.88
        }
    ]
    
    service = CredibilityService()
    results = await service.process_data(test_data)
    
    for item in results:
        print_result(item)
    
    passed = all(0.70 <= item['credibility_score'] <= 0.85 for item in results)
    print(f"\n{'✅ PASS' if passed else '❌ FAIL'}: All Tier 2 sources scored 0.70-0.85\n")
    
    return results


async def test_reddit_varying_quality():
    """Test Reddit posts with varying quality"""
    print_header("TEST 3: Reddit Posts - Varying Quality")
    
    test_data = [
        {
            "Post_ID": "reddit_high_quality",
            "Domain": "reddit.com",
            "Subreddit": "investing",
            "Author": "ValueInvestor2024",
            "clean_combined": "Detailed analysis of Tesla's Q4 2024 earnings. Revenue: $25.2B (+10% YoY), EPS: $1.19 vs $1.05 expected. Margins improved due to cost reduction. Source: Tesla IR.",
            "urls": ["https://ir.tesla.com"],
            "Score": 850,
            "Upvote_Ratio": 0.95,
            "Total_Comments": 156
        },
        {
            "Post_ID": "reddit_medium_quality",
            "Domain": "reddit.com",
            "Subreddit": "stocks",
            "Author": "StockWatcher99",
            "clean_combined": "Thoughts on AAPL after earnings? Looks bullish to me.",
            "urls": [],
            "Score": 45,
            "Upvote_Ratio": 0.75,
            "Total_Comments": 12
        },
        {
            "Post_ID": "reddit_low_quality",
            "Domain": "reddit.com",
            "Subreddit": "wallstreetbets",
            "Author": "YOLOKing420",
            "clean_combined": "GME to the moon!!! 🚀🚀🚀🚀🚀 Diamond hands!!! Trust me bro!!!",
            "urls": [],
            "Score": 3,
            "Upvote_Ratio": 0.52,
            "Total_Comments": 8
        }
    ]
    
    service = CredibilityService()
    results = await service.process_data(test_data)
    
    for item in results:
        print_result(item)
    
    # Validate ordering
    scores = [item['credibility_score'] for item in results]
    passed = scores[0] > scores[1] > scores[2]  # High > Medium > Low
    print(f"\n{'✅ PASS' if passed else '❌ FAIL'}: Reddit quality scoring works correctly\n")
    print(f"Scores: High={scores[0]:.3f}, Medium={scores[1]:.3f}, Low={scores[2]:.3f}\n")
    
    return results


async def test_content_quality_factors():
    """Test content quality analysis"""
    print_header("TEST 4: Content Quality Factors")
    
    test_data = [
        {
            "Post_ID": "content_high_quality",
            "Domain": "reddit.com",
            "Subreddit": "investing",
            "Author": "FinanceAnalyst",
            "clean_combined": "According to latest SEC filings, Microsoft reported revenue of $60B in Q3 FY2024, representing 15% growth YoY. Operating margin improved to 42% from 38% last year. Full analysis: https://sec.gov/...",
            "urls": ["https://sec.gov"],
            "Score": 200,
            "Upvote_Ratio": 0.93,
            "Total_Comments": 45
        },
        {
            "Post_ID": "content_low_quality",
            "Domain": "reddit.com",
            "Subreddit": "stocks",
            "Author": "RandomUser",
            "clean_combined": "Stock go up!!!",
            "urls": [],
            "Score": 2,
            "Upvote_Ratio": 0.60,
            "Total_Comments": 1
        }
    ]
    
    service = CredibilityService()
    results = await service.process_data(test_data)
    
    for item in results:
        print_result(item)
    
    passed = results[0]['content_credibility'] > results[1]['content_credibility']
    print(f"\n{'✅ PASS' if passed else '❌ FAIL'}: Content quality scoring works\n")
    
    return results


async def test_unknown_sources():
    """Test unknown/suspicious sources"""
    print_header("TEST 5: Unknown Sources (Should Score Low)")
    
    test_data = [
        {
            "Post_ID": "unknown_source",
            "Domain": "randomfinanceblog.com",
            "Author": "Unknown",
            "clean_combined": "Breaking news: Stock market will crash tomorrow!!! Shocking revelation!!!",
            "urls": [],
            "Score": 1,
            "Upvote_Ratio": 0.45
        }
    ]
    
    service = CredibilityService()
    results = await service.process_data(test_data)
    
    for item in results:
        print_result(item)
    
    passed = results[0]['credibility_score'] < 0.4
    print(f"\n{'✅ PASS' if passed else '❌ FAIL'}: Unknown sources scored low (<0.4)\n")
    
    return results


async def test_with_actual_data():
    """Test with actual cleaned_dummy.json if available"""
    print_header("TEST 6: Process Actual Data (if available)")
    
    data_path = Path(__file__).parent.parent / "data" / "cleaned_dummy.json"
    
    if not data_path.exists():
        print("⚠️  cleaned_dummy.json not found - skipping this test")
        return []
    
    try:
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"Loaded {len(data)} items from cleaned_dummy.json")
        
        # Process first 10 items
        sample = data[:10]
        service = CredibilityService(enable_llm=False)
        results = await service.process_data(sample)
        
        # Show summary
        print("\nSample Results (first 5):\n")
        for item in results[:5]:
            print(f"{item.get('Post_ID'):<15} | "
                  f"Score: {item['credibility_score']:.3f} | "
                  f"Tier: {item['source_tier']:<20} | "
                  f"Source: {item.get('Domain', 'N/A')}")
        
        # Statistics
        scores = [item['credibility_score'] for item in results]
        print(f"\nScore Statistics:")
        print(f"  Average: {sum(scores)/len(scores):.3f}")
        print(f"  Min: {min(scores):.3f}")
        print(f"  Max: {max(scores):.3f}")
        
        # Save results
        output_path = data_path.parent / "credibility_analyzed.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✅ Saved results to: {output_path}\n")
        
        return results
        
    except Exception as e:
        print(f"❌ Error processing actual data: {e}\n")
        return []


async def test_performance():
    """Test processing performance"""
    print_header("TEST 7: Performance Test")
    
    import time
    
    # Generate 100 test items
    test_data = []
    for i in range(100):
        test_data.append({
            "Post_ID": f"perf_test_{i}",
            "Domain": "reddit.com",
            "Subreddit": "stocks",
            "Author": f"User{i}",
            "clean_combined": f"Test content for performance testing item {i}. This is a longer text to simulate real posts.",
            "urls": [],
            "Score": i * 5,
            "Upvote_Ratio": 0.80,
            "Total_Comments": i
        })
    
    service = CredibilityService()
    
    start_time = time.time()
    results = await service.process_data(test_data)
    duration = time.time() - start_time
    
    avg_time = duration / len(results) * 1000  # ms per item
    
    print(f"Processed {len(results)} items in {duration:.2f} seconds")
    print(f"Average: {avg_time:.1f} ms per item")
    
    passed = avg_time < 50  # Should process in < 50ms per item
    print(f"\n{'✅ PASS' if passed else '❌ FAIL'}: Performance acceptable (<50ms per item)\n")
    
    return results


async def run_all_tests():
    """Run all tests"""
    print("\n" + "🎯"*50)
    print(" "*70 + "CREDIBILITY SERVICE TEST SUITE")
    print("🎯"*50 + "\n")
    
    all_passed = True
    
    try:
        # Test 1: Tier 1 sources
        await test_tier_1_sources()
        
        # Test 2: Tier 2 sources
        await test_tier_2_sources()
        
        # Test 3: Reddit varying quality
        await test_reddit_varying_quality()
        
        # Test 4: Content quality
        await test_content_quality_factors()
        
        # Test 5: Unknown sources
        await test_unknown_sources()
        
        # Test 6: Actual data
        await test_with_actual_data()
        
        # Test 7: Performance
        await test_performance()
        
    except Exception as e:
        logger.error(f"Test suite error: {e}")
        all_passed = False
    
    # Summary
    print("\n" + "🏆"*50)
    print(" "*70 + "TEST SUITE COMPLETE")
    print("🏆"*50 + "\n")
    
    if all_passed:
        print("✅ All tests completed successfully!")
    else:
        print("⚠️  Some tests failed - review output above")
    
    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(run_all_tests())