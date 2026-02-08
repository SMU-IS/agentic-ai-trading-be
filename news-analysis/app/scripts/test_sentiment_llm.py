"""
Test Suite for LLM-Based Sentiment Analysis Service (Gemini)
File: news-analysis/app/scripts/test_sentiment_llm.py

Run with: python -m app.scripts.test_sentiment_llm
From news-analysis directory: cd news-analysis && python -m app.scripts.test_sentiment_llm
"""

import asyncio
import json
import logging
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services._05b_sentiment_llm import LLMSentimentService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_single_ticker_sentiment():
    """Test sentiment analysis for a single ticker"""
    print("\n" + "=" * 80)
    print("TEST 1: Single Ticker Sentiment Analysis")
    print("=" * 80)

    service = LLMSentimentService()

    test_item = {
        'content': {
            'clean_combined_withurl': """
            Apple just crushed earnings! Revenue up 15% YoY. The iPhone sales exceeded
            all expectations. Tim Cook mentioned strong growth in services.
            AAPL is going to the moon! 🚀🚀🚀
            """
        },
        'ticker_metadata': {
            'AAPL': {
                'OfficialName': 'Apple Inc.',
                'event_type': 'Earnings Report'
            }
        }
    }

    print("\nInput:")
    print(f"  Text: {test_item['content']['clean_combined_withurl'][:100]}...")
    print(f"  Tickers: {list(test_item['ticker_metadata'].keys())}")

    try:
        result = await service.analyse(test_item)

        sentiment_analysis = result.get('sentiment_analysis', {})
        print("\nResults:")
        print(f"  Overall Score: {sentiment_analysis.get('overall_sentiment_score')}")
        print(f"  Overall Label: {sentiment_analysis.get('overall_sentiment_label')}")
        print(f"  Analysis Successful: {sentiment_analysis.get('analysis_successful')}")

        ticker_sentiments = sentiment_analysis.get('ticker_sentiments', {})
        for ticker, data in ticker_sentiments.items():
            print(f"\n  {ticker} ({data.get('official_name')}):")
            print(f"    Score: {data.get('sentiment_score')}")
            print(f"    Label: {data.get('sentiment_label')}")
            print(f"    Raw LLM Confidence: {data.get('raw_llm_confidence')}")
            print(f"    Calibrated Confidence: {data.get('confidence')}")
            print(f"    Reasoning: {data.get('reasoning')}")

        # Validation
        aapl_sentiment = ticker_sentiments.get('AAPL', {})
        passed = (
            aapl_sentiment.get('sentiment_label') == 'positive' and
            aapl_sentiment.get('sentiment_score', 0) > 0.3
        )

        print(f"\n{'✓ PASS' if passed else '✗ FAIL'}: Expected positive sentiment for AAPL")
        return passed

    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        return False


async def test_multi_ticker_sentiment():
    """Test sentiment analysis for multiple tickers with different sentiments"""
    print("\n" + "=" * 80)
    print("TEST 2: Multi-Ticker Sentiment Analysis (Different Sentiments)")
    print("=" * 80)

    service = LLMSentimentService()

    test_item = {
        'content': {
            'clean_combined_withurl': """
            Apple just crushed earnings! Revenue up 15% YoY while Microsoft struggles
            with cloud growth slowdown. AAPL is going to the moon 🚀🚀🚀
            Meanwhile, MSFT looks bearish short-term due to Azure deceleration.
            I'm selling my Microsoft position but diamond hands on Apple! 💎🙌
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

    print("\nInput:")
    print(f"  Text: {test_item['content']['clean_combined_withurl'][:150]}...")
    print(f"  Tickers: {list(test_item['ticker_metadata'].keys())}")

    try:
        result = await service.analyse(test_item)

        sentiment_analysis = result.get('sentiment_analysis', {})
        print("\nResults:")
        print(f"  Overall Score: {sentiment_analysis.get('overall_sentiment_score')}")
        print(f"  Overall Label: {sentiment_analysis.get('overall_sentiment_label')}")

        ticker_sentiments = sentiment_analysis.get('ticker_sentiments', {})
        for ticker, data in ticker_sentiments.items():
            print(f"\n  {ticker} ({data.get('official_name')}):")
            print(f"    Score: {data.get('sentiment_score')}")
            print(f"    Label: {data.get('sentiment_label')}")
            print(f"    Raw LLM Confidence: {data.get('raw_llm_confidence')}")
            print(f"    Calibrated Confidence: {data.get('confidence')}")
            print(f"    Reasoning: {data.get('reasoning')}")

        # Validation: AAPL should be positive, MSFT should be negative
        aapl = ticker_sentiments.get('AAPL', {})
        msft = ticker_sentiments.get('MSFT', {})

        aapl_correct = aapl.get('sentiment_label') == 'positive'
        msft_correct = msft.get('sentiment_label') == 'negative'

        print(f"\n{'✓ PASS' if aapl_correct else '✗ FAIL'}: AAPL should be positive")
        print(f"{'✓ PASS' if msft_correct else '✗ FAIL'}: MSFT should be negative")

        return aapl_correct and msft_correct

    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        return False


async def test_neutral_sentiment():
    """Test neutral/factual content"""
    print("\n" + "=" * 80)
    print("TEST 3: Neutral/Factual Content")
    print("=" * 80)

    service = LLMSentimentService()

    test_item = {
        'content': {
            'clean_combined_withurl': """
            Tesla Inc. announced it will hold its annual shareholder meeting on May 15th.
            The meeting will be held at the company's headquarters in Austin, Texas.
            Shareholders of record as of April 1st will be eligible to vote.
            """
        },
        'ticker_metadata': {
            'TSLA': {
                'OfficialName': 'Tesla Inc.',
                'event_type': 'Corporate Announcement'
            }
        }
    }

    print("\nInput:")
    print(f"  Text: {test_item['content']['clean_combined_withurl'][:100]}...")

    try:
        result = await service.analyse(test_item)

        sentiment_analysis = result.get('sentiment_analysis', {})
        ticker_sentiments = sentiment_analysis.get('ticker_sentiments', {})

        tsla = ticker_sentiments.get('TSLA', {})
        print(f"\nResults:")
        print(f"  TSLA Score: {tsla.get('sentiment_score')}")
        print(f"  TSLA Label: {tsla.get('sentiment_label')}")
        print(f"  Reasoning: {tsla.get('reasoning')}")

        # Score should be in neutral range (-0.1 to 0.1)
        score = tsla.get('sentiment_score', 1)
        is_neutral = -0.3 <= score <= 0.3  # Allow some flexibility

        print(f"\n{'✓ PASS' if is_neutral else '✗ FAIL'}: Expected neutral-ish sentiment (score: {score})")
        return is_neutral

    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        return False


async def test_strong_negative_sentiment():
    """Test strongly negative content"""
    print("\n" + "=" * 80)
    print("TEST 4: Strong Negative Sentiment")
    print("=" * 80)

    service = LLMSentimentService()

    test_item = {
        'content': {
            'clean_combined_withurl': """
            BREAKING: SEC charges XYZ Corp with massive fraud!
            CEO arrested, stock halted. This is a complete disaster.
            Investors are getting rekt. Total rugpull! 💀📉
            Sell everything immediately. This company is done.
            """
        },
        'ticker_metadata': {
            'XYZ': {
                'OfficialName': 'XYZ Corporation',
                'event_type': 'Legal/Regulatory'
            }
        }
    }

    print("\nInput:")
    print(f"  Text: {test_item['content']['clean_combined_withurl'][:100]}...")

    try:
        result = await service.analyse(test_item)

        sentiment_analysis = result.get('sentiment_analysis', {})
        ticker_sentiments = sentiment_analysis.get('ticker_sentiments', {})

        xyz = ticker_sentiments.get('XYZ', {})
        print(f"\nResults:")
        print(f"  XYZ Score: {xyz.get('sentiment_score')}")
        print(f"  XYZ Label: {xyz.get('sentiment_label')}")
        print(f"  Confidence: {xyz.get('confidence')}")
        print(f"  Reasoning: {xyz.get('reasoning')}")

        # Should be strongly negative
        score = xyz.get('sentiment_score', 0)
        is_negative = score < -0.5

        print(f"\n{'✓ PASS' if is_negative else '✗ FAIL'}: Expected strong negative (score < -0.5, got {score})")
        return is_negative

    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        return False


async def test_reddit_slang():
    """Test Reddit/WSB slang recognition"""
    print("\n" + "=" * 80)
    print("TEST 5: Reddit/WSB Slang Recognition")
    print("=" * 80)

    service = LLMSentimentService()

    test_item = {
        'content': {
            'clean_combined_withurl': """
            GME to the moon! 🚀🚀🚀 Diamond hands boys! 💎🙌
            HODL the line, tendies incoming! Apes together strong!
            This is not financial advice but I'm YOLO'ing my life savings.
            """
        },
        'ticker_metadata': {
            'GME': {
                'OfficialName': 'GameStop Corp.',
                'event_type': 'Social Media Sentiment'
            }
        }
    }

    print("\nInput:")
    print(f"  Text: {test_item['content']['clean_combined_withurl'][:100]}...")

    try:
        result = await service.analyse(test_item)

        sentiment_analysis = result.get('sentiment_analysis', {})
        ticker_sentiments = sentiment_analysis.get('ticker_sentiments', {})

        gme = ticker_sentiments.get('GME', {})
        print(f"\nResults:")
        print(f"  GME Score: {gme.get('sentiment_score')}")
        print(f"  GME Label: {gme.get('sentiment_label')}")
        print(f"  Reasoning: {gme.get('reasoning')}")

        # Should recognize bullish slang
        is_positive = gme.get('sentiment_label') == 'positive'

        print(f"\n{'✓ PASS' if is_positive else '✗ FAIL'}: Expected positive (Reddit bullish slang)")
        return is_positive

    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        return False


async def test_pipeline_data_structure():
    """Test with realistic pipeline data structure"""
    print("\n" + "=" * 80)
    print("TEST 6: Realistic Pipeline Data Structure")
    print("=" * 80)

    service = LLMSentimentService()

    # Simulating data as it would come from event identification
    test_item = {
        'Post_ID': 'abc123',
        'subreddit': 'wallstreetbets',
        'Author': 'test_user',
        'Created_UTC': 1704067200,
        'URL': 'https://reddit.com/r/wallstreetbets/abc123',
        'content': {
            'clean_title': 'NVDA earnings tomorrow - predictions?',
            'clean_combined_withurl': """
            NVDA earnings tomorrow - predictions?

            I think Nvidia is going to crush it. AI demand is insane.
            Jensen is a genius. Data center revenue will be massive.
            Already up 200% this year but I think there's more room to run.
            Loading up on calls! 🚀
            """,
            'clean_combined_withouturl': """
            NVDA earnings tomorrow - predictions?

            I think Nvidia is going to crush it. AI demand is insane.
            Jensen is a genius. Data center revenue will be massive.
            """
        },
        'ticker_metadata': {
            'NVDA': {
                'OfficialName': 'NVIDIA Corporation',
                'NameIdentified': ['Nvidia', 'NVDA', 'Jensen'],
                'event_type': 'Earnings Report',
                'event_proposal': 'Quarterly earnings announcement'
            }
        }
    }

    print("\nInput (simulated pipeline data):")
    print(f"  Post ID: {test_item['Post_ID']}")
    print(f"  Subreddit: {test_item['subreddit']}")
    print(f"  Tickers: {list(test_item['ticker_metadata'].keys())}")

    try:
        result = await service.analyse(test_item)

        # Check that ticker_metadata was enriched
        enriched_ticker = result.get('ticker_metadata', {}).get('NVDA', {})

        print("\nEnriched ticker_metadata['NVDA']:")
        print(f"  sentiment_score: {enriched_ticker.get('sentiment_score')}")
        print(f"  sentiment_label: {enriched_ticker.get('sentiment_label')}")
        print(f"  sentiment_confidence: {enriched_ticker.get('sentiment_confidence')}")
        print(f"  sentiment_reasoning: {enriched_ticker.get('sentiment_reasoning')}")

        sentiment_analysis = result.get('sentiment_analysis', {})
        print(f"\nsentiment_analysis:")
        print(f"  overall_sentiment_score: {sentiment_analysis.get('overall_sentiment_score')}")
        print(f"  overall_sentiment_label: {sentiment_analysis.get('overall_sentiment_label')}")
        print(f"  analysis_successful: {sentiment_analysis.get('analysis_successful')}")

        # Validation
        has_enriched_data = (
            'sentiment_score' in enriched_ticker and
            'sentiment_label' in enriched_ticker and
            'sentiment_confidence' in enriched_ticker and
            'sentiment_reasoning' in enriched_ticker
        )

        print(f"\n{'✓ PASS' if has_enriched_data else '✗ FAIL'}: ticker_metadata properly enriched")
        return has_enriched_data

    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_cleaned_dummy_json(max_posts: int = 5):
    """Test with actual cleaned_dummy.json data

    Args:
        max_posts: Maximum number of posts to process (default: 5)
    """
    print("\n" + "=" * 80)
    print("TEST 7: Processing cleaned_dummy.json")
    print("=" * 80)

    # Path to cleaned_dummy.json
    json_path = Path(__file__).parent.parent / "data" / "cleaned_dummy.json"

    if not json_path.exists():
        print(f"\n⚠ SKIP: {json_path} not found")
        return None

    # Common ticker patterns to detect
    TICKER_MAP = {
        'AAPL': {'OfficialName': 'Apple Inc.', 'aliases': ['apple', 'aapl', '$aapl']},
        'MSFT': {'OfficialName': 'Microsoft Corporation', 'aliases': ['microsoft', 'msft', '$msft', 'azure']},
        'TSLA': {'OfficialName': 'Tesla Inc.', 'aliases': ['tesla', 'tsla', '$tsla']},
        'AMZN': {'OfficialName': 'Amazon.com Inc.', 'aliases': ['amazon', 'amzn', '$amzn']},
        'NVDA': {'OfficialName': 'NVIDIA Corporation', 'aliases': ['nvidia', 'nvda', '$nvda']},
        'META': {'OfficialName': 'Meta Platforms Inc.', 'aliases': ['meta', 'facebook', '$meta']},
        'GOOGL': {'OfficialName': 'Alphabet Inc.', 'aliases': ['google', 'alphabet', 'googl', '$googl']},
        'AMD': {'OfficialName': 'Advanced Micro Devices Inc.', 'aliases': ['amd', '$amd']},
        'INTC': {'OfficialName': 'Intel Corporation', 'aliases': ['intel', 'intc', '$intc']},
        'NFLX': {'OfficialName': 'Netflix Inc.', 'aliases': ['netflix', 'nflx', '$nflx']},
        'BA': {'OfficialName': 'Boeing Company', 'aliases': ['boeing', 'ba', '$ba']},
        'JPM': {'OfficialName': 'JPMorgan Chase & Co.', 'aliases': ['jpmorgan', 'jpm', '$jpm']},
        'BAC': {'OfficialName': 'Bank of America Corp.', 'aliases': ['bank of america', 'bac', '$bac']},
        'SHOP': {'OfficialName': 'Shopify Inc.', 'aliases': ['shopify', 'shop', '$shop']},
        'GME': {'OfficialName': 'GameStop Corp.', 'aliases': ['gamestop', 'gme', '$gme']},
        'BTC': {'OfficialName': 'Bitcoin', 'aliases': ['bitcoin', 'btc', '$btc']},
    }

    def detect_tickers(text: str) -> dict:
        """Detect tickers mentioned in text and create ticker_metadata"""
        text_lower = text.lower()
        detected = {}

        for ticker, info in TICKER_MAP.items():
            for alias in info['aliases']:
                if alias in text_lower:
                    detected[ticker] = {
                        'OfficialName': info['OfficialName'],
                        'NameIdentified': [alias],
                        'event_type': 'News/Social Media'
                    }
                    break

        return detected

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"\nLoaded {len(data)} posts from cleaned_dummy.json")
        print(f"Will process up to {max_posts} posts with detected tickers")

        service = LLMSentimentService()

        # Process items that have detectable tickers
        processed = 0
        results = []
        max_to_process = max_posts

        for item in data:
            if processed >= max_to_process:
                break

            text = item.get('clean_combined', '')
            ticker_metadata = detect_tickers(text)

            if not ticker_metadata:
                continue  # Skip posts with no detected tickers

            # Transform to pipeline format - include ALL original data
            # This simulates the full pipeline data structure
            pipeline_item = {
                # Original post data
                'Post_ID': item.get('Post_ID', 'unknown'),
                'Post_URL': item.get('Post_URL', ''),
                'Author': item.get('Author', ''),
                'Timestamp_UTC': item.get('Timestamp_UTC'),
                'Timestamp_ISO': item.get('Timestamp_ISO'),
                'Total_Comments': item.get('Total_Comments', 0),
                'Score': item.get('Score', 0),
                'Upvote_Ratio': item.get('Upvote_Ratio', 0),
                'Subreddit': item.get('Subreddit', 'unknown'),
                'Domain': item.get('Domain', ''),
                'urls': item.get('urls', []),
                'images': item.get('images', []),
                # Content structure (as it would be from preprocessor)
                'content': {
                    'clean_title': item.get('clean_title', ''),
                    'clean_body': item.get('clean_body', ''),
                    'clean_combined': item.get('clean_combined', ''),
                    'clean_combined_withurl': text,
                    'clean_combined_withouturl': item.get('clean_combined', ''),
                },
                # Ticker metadata (as it would be from ticker identification)
                'ticker_metadata': ticker_metadata
            }

            print(f"\n{'─' * 60}")
            print(f"Post {processed + 1}: {item.get('Post_ID')}")
            print(f"Subreddit: {item.get('Subreddit')}")
            print(f"Detected Tickers: {list(ticker_metadata.keys())}")
            print(f"Text: {text[:100]}...")

            try:
                # Analyse returns the FULL enriched item with sentiment data appended
                enriched_result = await service.analyse(pipeline_item)
                sentiment_analysis = enriched_result.get('sentiment_analysis', {})

                print(f"\nSentiment Results:")
                print(f"  Overall: {sentiment_analysis.get('overall_sentiment_label')} "
                      f"({sentiment_analysis.get('overall_sentiment_score')})")

                for ticker, sdata in sentiment_analysis.get('ticker_sentiments', {}).items():
                    print(f"  {ticker}: {sdata.get('sentiment_label')} "
                          f"(score={sdata.get('sentiment_score')}, "
                          f"conf={sdata.get('confidence')})")
                    print(f"    Reasoning: {sdata.get('reasoning', '')[:80]}...")

                # Save the FULL enriched result (original data + sentiment analysis)
                results.append(enriched_result)

                processed += 1

            except Exception as e:
                print(f"  ✗ Error: {e}")
                # Even on error, include original data with error info
                pipeline_item['sentiment_analysis'] = {
                    'error': str(e),
                    'analysis_successful': False,
                    'ticker_sentiments': {}
                }
                results.append(pipeline_item)
                processed += 1

        # Save results - full enriched pipeline data
        output_path = json_path.parent / "test_sentiment_llm_results.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n{'─' * 60}")
        print(f"✓ Processed {processed} posts")
        print(f"✓ Results saved to: {output_path}")

        # Summary - check analysis_successful in sentiment_analysis
        successful = sum(
            1 for r in results
            if r.get('sentiment_analysis', {}).get('analysis_successful', False)
        )
        print(f"\nSuccess rate: {successful}/{processed}")

        # Show structure of first result
        if results:
            print(f"\nOutput data structure (keys):")
            print(f"  Top-level: {list(results[0].keys())}")
            if 'ticker_metadata' in results[0]:
                first_ticker = next(iter(results[0]['ticker_metadata'].keys()), None)
                if first_ticker:
                    print(f"  ticker_metadata['{first_ticker}']: {list(results[0]['ticker_metadata'][first_ticker].keys())}")
            if 'sentiment_analysis' in results[0]:
                print(f"  sentiment_analysis: {list(results[0]['sentiment_analysis'].keys())}")

        return successful == processed

    except Exception as e:
        print(f"\n✗ FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 80)
    print(" " * 20 + "LLM SENTIMENT ANALYSIS TEST SUITE")
    print(" " * 20 + "(Gemini 2.5 Flash Lite)")
    print("=" * 80)

    results = []

    # Run all tests
    results.append(("Single Ticker", await test_single_ticker_sentiment()))
    results.append(("Multi Ticker", await test_multi_ticker_sentiment()))
    results.append(("Neutral Content", await test_neutral_sentiment()))
    results.append(("Strong Negative", await test_strong_negative_sentiment()))
    results.append(("Reddit Slang", await test_reddit_slang()))
    results.append(("Pipeline Structure", await test_pipeline_data_structure()))

    # Test with cleaned_dummy.json
    dummy_result = await test_cleaned_dummy_json()
    if dummy_result is not None:
        results.append(("cleaned_dummy.json", dummy_result))

    # Summary
    print("\n" + "=" * 80)
    print(" " * 30 + "TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")

    print(f"\n  Total: {passed}/{len(results)} passed")
    print(f"  Success Rate: {passed/len(results)*100:.0f}%")
    print("=" * 80 + "\n")

    return passed == len(results)


async def run_json_test_only(max_posts: int = 5):
    """Run only the cleaned_dummy.json test"""
    print("\n" + "=" * 80)
    print(" " * 15 + "LLM SENTIMENT - cleaned_dummy.json TEST")
    print(" " * 20 + "(Gemini 2.5 Flash Lite)")
    print("=" * 80)

    result = await test_cleaned_dummy_json(max_posts=max_posts)

    if result is None:
        print("\n⚠ Test skipped (file not found)")
        return False
    elif result:
        print("\n✓ All posts processed successfully")
        return True
    else:
        print("\n✗ Some posts failed to process")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LLM Sentiment Analysis Test Suite")
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Run only the cleaned_dummy.json test"
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=5,
        help="Maximum number of posts to process from cleaned_dummy.json (default: 5)"
    )

    args = parser.parse_args()

    if args.json_only:
        success = asyncio.run(run_json_test_only(max_posts=args.max_posts))
    else:
        success = asyncio.run(run_all_tests())

    sys.exit(0 if success else 1)
