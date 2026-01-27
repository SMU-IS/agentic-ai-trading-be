"""
Test Suite for Sentiment Analysis Service
File: news-analysis/app/scripts/test_sentiment.py

Run with: python -m app.scripts.test_sentiment
"""

import json
import logging
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services._05_sentiment import sentiment_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_individual_texts():
    """Test individual text analysis"""
    print("\n" + "="*80)
    print("TEST 1: Individual Text Analysis")
    print("="*80)
    
    test_cases = [
        {
            "text": "Apple reports strong Q4 earnings & beats expectations 🚀",
            "expected": "positive"
        },
        {
            "text": "Microsoft cloud growth slows < analysts expected",
            "expected": "negative"
        },
        {
            "text": "TSLA to the moon! 🚀📈💎🙌",
            "expected": "positive"
        },
        {
            "text": "Market crash incoming 📉😭",
            "expected": "negative"
        },
        {
            "text": "The company held a quarterly meeting",
            "expected": "neutral"
        }
    ]
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(test_cases, 1):
        result = sentiment_service.analyze_text(case["text"])
        
        status = "✓ PASS" if result.sentiment_label == case["expected"] else "✗ FAIL"
        if result.sentiment_label == case["expected"]:
            passed += 1
        else:
            failed += 1
        
        print(f"\n[Test {i}] {status}")
        print(f"Text: {case['text'][:60]}...")
        print(f"Expected: {case['expected']} | Got: {result.sentiment_label}")
        print(f"Score: {result.sentiment_score:.4f} | Confidence: {result.confidence:.4f}")
        print(f"Models: {', '.join(result.models_used)}")
    
    print(f"\n{'='*80}")
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print(f"{'='*80}\n")
    
    return passed, failed


def test_batch_processing():
    """Test batch processing with sample data"""
    print("\n" + "="*80)
    print("TEST 2: Batch Processing")
    print("="*80)
    
    sample_data = [
        {
            "Post_ID": "test1",
            "clean_combined": "Apple reports strong Q4 earnings & beats expectations 🚀. Apple Inc. ($AAPL) just reported earnings."
        },
        {
            "Post_ID": "test2",
            "clean_combined": "Microsoft cloud growth slows < analysts expected. Reuters: Microsoft Azure growth slowed in Q4."
        },
        {
            "Post_ID": "test3",
            "clean_combined": "Diamond hands 💎🙌 HODL to the moon! 🚀🚀🚀"
        },
        {
            "Post_ID": "test4",
            "clean_combined": "Lost everything on this trade 📉😭💀"
        },
        {
            "Post_ID": "test5",
            "clean_combined": "The market opened at 9:30 AM today"
        }
    ]
    
    # Process batch
    results = sentiment_service.process_batch(sample_data)
    
    print(f"\nProcessed {len(results)} items:\n")
    
    for item in results:
        print(f"Post ID: {item['Post_ID']}")
        print(f"Text: {item['clean_combined'][:60]}...")
        print(f"Sentiment: {item['sentiment_label'].upper()}")
        print(f"Score: {item['sentiment_score']:.4f}")
        print(f"Confidence: {item['confidence']:.4f}")
        print(f"Models: {', '.join(item['models_used'])}")
        print("-"*80)
    
    # Verify all items have sentiment fields
    required_fields = ['sentiment_score', 'sentiment_label', 'confidence', 'models_used']
    all_valid = all(
        all(field in item for field in required_fields)
        for item in results
    )
    
    print(f"\n{'='*80}")
    print(f"Batch Processing: {'✓ PASS' if all_valid else '✗ FAIL'}")
    print(f"{'='*80}\n")
    
    return all_valid


def test_with_actual_json():
    """Test with actual cleaned_dummy.json if it exists"""
    print("\n" + "="*80)
    print("TEST 3: Processing Actual cleaned_dummy.json")
    print("="*80)
    
    # Look for the JSON file in data directory
    json_path = Path(__file__).parent.parent.parent / "app" / "data" / "cleaned_dummy.json"
    
    if not json_path.exists():
        print(f"\n⚠ Skipping: {json_path} not found")
        return None
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"\nLoaded {len(data)} items from {json_path.name}")
        
        # Process first 10 items as a test
        sample = data[:10] if len(data) > 10 else data
        results = sentiment_service.process_batch(sample)
        
        print(f"\nSample Results (first 5):\n")
        for item in results[:5]:
            print(f"Post ID: {item.get('Post_ID', 'unknown')}")
            print(f"Sentiment: {item['sentiment_label'].upper()} ({item['sentiment_score']:.4f})")
            print(f"Confidence: {item['confidence']:.4f}")
            print("-"*80)
        
        # Save results to output file
        output_path = json_path.parent / "sentiment_analyzed.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✓ Saved results to: {output_path}")
        print(f"{'='*80}\n")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error processing JSON: {e}")
        return False


def test_edge_cases():
    """Test edge cases"""
    print("\n" + "="*80)
    print("TEST 4: Edge Cases")
    print("="*80)
    
    edge_cases = [
        {"text": "🚀🚀🚀📈📈", "desc": "Emoji only"},
        {"text": "Check out $TSLA $AAPL $MSFT today", "desc": "Tickers only"},
        {"text": "A" * 5000, "desc": "Very long text"},
        {"text": "bull bear bull bear neutral", "desc": "Conflicting signals"},
        {"text": "YOLO diamond hands to the moon! 🚀💎🙌", "desc": "Reddit slang"},
    ]
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(edge_cases, 1):
        try:
            result = sentiment_service.analyze_text(case["text"])
            print(f"\n[Test {i}] ✓ {case['desc']}")
            print(f"Label: {result.sentiment_label} | Score: {result.sentiment_score:.4f}")
            passed += 1
        except Exception as e:
            print(f"\n[Test {i}] ✗ {case['desc']}")
            print(f"Error: {e}")
            failed += 1
    
    print(f"\n{'='*80}")
    print(f"Edge Cases: {passed} passed, {failed} failed")
    print(f"{'='*80}\n")
    
    return passed, failed


def test_emoji_recognition():
    """Test specific emoji recognition"""
    print("\n" + "="*80)
    print("TEST 5: Emoji Recognition")
    print("="*80)
    
    emoji_tests = [
        ("Stock going up 📈", "Should detect bullish"),
        ("Stock crashing 📉", "Should detect bearish"),
        ("To the moon! 🚀🚀🚀", "Should detect very bullish"),
        ("Diamond hands 💎🙌", "Should detect bullish/holding"),
        ("Paper hands 🧻👋", "Should detect bearish/selling"),
    ]
    
    for text, expectation in emoji_tests:
        result = sentiment_service.analyze_text(text)
        emoji_influence = result.emoji_influence
        
        print(f"\nText: {text}")
        print(f"Expectation: {expectation}")
        print(f"Result: {result.sentiment_label} (emoji influence: {emoji_influence:.2%})")
        print(f"Models: {', '.join(result.models_used)}")
    
    print(f"\n{'='*80}\n")


def run_all_tests():
    """Run all tests"""
    print("\n" + "🎯"*40)
    print(" "*30 + "SENTIMENT ANALYSIS TEST SUITE")
    print("🎯"*40 + "\n")
    
    total_passed = 0
    total_failed = 0
    
    # Test 1: Individual texts
    passed, failed = test_individual_texts()
    total_passed += passed
    total_failed += failed
    
    # Test 2: Batch processing
    batch_result = test_batch_processing()
    if batch_result:
        total_passed += 1
    else:
        total_failed += 1
    
    # Test 3: Actual JSON
    json_result = test_with_actual_json()
    if json_result is not None:
        if json_result:
            total_passed += 1
        else:
            total_failed += 1
    
    # Test 4: Edge cases
    passed, failed = test_edge_cases()
    total_passed += passed
    total_failed += failed
    
    # Test 5: Emoji recognition
    test_emoji_recognition()
    
    # Final summary
    print("\n" + "🏆"*40)
    print(" "*30 + "FINAL TEST SUMMARY")
    print("🏆"*40)
    print(f"\nTotal Tests Passed: {total_passed}")
    print(f"Total Tests Failed: {total_failed}")
    print(f"Success Rate: {total_passed/(total_passed+total_failed)*100:.1f}%")
    print("\n" + "🏆"*40 + "\n")


if __name__ == "__main__":
    run_all_tests()