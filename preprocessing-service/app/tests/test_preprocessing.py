"""
Unit Tests — PreprocessingService

Run from project root:
    python -m pytest app/tests/test_preprocessing.py -v
"""

import pytest
from app.services._01_preprocesser import PreprocessingService


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def service():
    return PreprocessingService()


# ============================================================
# clean_text() Tests
# ============================================================


def test_clean_text_basic(service):
    text = " Hello   world! \n"
    result = service.clean_text(text)

    assert result == "Hello world!"


def test_clean_text_remove_urls(service):
    text = "Check this https://example.com"
    result = service.clean_text(text, remove_urls=True)

    assert "https://example.com" not in result


def test_clean_text_keep_urls(service):
    text = "[Google](https://google.com)"
    result = service.clean_text(text, remove_urls=False)

    # Markdown should become "Google: https://google.com"
    assert "Google:" in result
    assert "https://google.com" in result


def test_html_unescape(service):
    text = "Fish &amp; Chips &lt;3"
    result = service.clean_text(text)

    assert "&amp;" not in result
    assert "&lt;" not in result
    assert "Fish & Chips <3" == result

def test_ftfy_fix_text(service):
    # "cafÃ©" is a common mojibake example
    text = "I love cafÃ©"
    result = service.clean_text(text)

    assert "cafÃ©" not in result
    # After ftfy, it should become correct unicode
    assert "café" in result

def test_unicode_normalization(service):
    # Fullwidth "Ａ" (not normal ASCII A)
    text = "Ａ"

    result = service.clean_text(text)

    # After NFKC normalization, it becomes normal "A"
    assert result == "A"


# ============================================================
# preprocess_post() Tests
# ============================================================

def test_preprocess_post_full(service):
    dummy_post = {
        "id": "reddit:1rintl1", 
        "content_type": "post", 
        "native_id": "1rintl1", 
        "source": "reddit_batch", 
        "author": "NojaQu", 
        "url": "https://i.redd.it/4w98jvn7jlmg1.jpeg", 
        "timestamps": "2026-03-02T16:55:48+08:00", 
        "content": {
            "title": "Ａpple announces new iPhone 15 release & pre-order starts soon 🍏", 
            "body": "Ａpple's event showcased the iPhone 15 lineup.\n\nEvent stream: https://www.apple.com/apple-events\nTech review images: ![iPhone15](https://images.apple.com/iphone15.jpg)\nBlog coverage: www.techcrunch.com/apple-iphone-15\nSummary: <b>Improved battery life</b>, new camera features, iOS 18 included.\nEmoji reaction: 😍👍"
        }, 
        "engagement": {
            "total_comments": 10, 
            "score": 45, 
            "upvote_ratio": 0.83
            }, 
        "metadata": {
            "subreddit": "wallstreetbets", 
            "category": ""
        }
    }

    correct = {
        "id": "reddit:1rintl1", 
        "content_type": "post", 
        "native_id": "1rintl1", 
        "source": "reddit_batch", 
        "author": "NojaQu", 
        "url": "https://i.redd.it/4w98jvn7jlmg1.jpeg", 
        "timestamps": "2026-03-02T16:55:48+08:00", 
        "links": ["https://www.apple.com/apple-events", "www.techcrunch.com/apple-iphone-15"],
        "images": ["https://images.apple.com/iphone15.jpg", "https://i.redd.it/4w98jvn7jlmg1.jpeg"],
        "content": {
            "raw_title": "Ａpple announces new iPhone 15 release & pre-order starts soon 🍏",
            "raw_body": "Ａpple's event showcased the iPhone 15 lineup.\n\nEvent stream: https://www.apple.com/apple-events\nTech review images: ![iPhone15](https://images.apple.com/iphone15.jpg)\nBlog coverage: www.techcrunch.com/apple-iphone-15\nSummary: <b>Improved battery life</b>, new camera features, iOS 18 included.\nEmoji reaction: 😍👍",
            "clean_title": "Apple announces new iPhone 15 release & pre-order starts soon :green_apple:",
            "clean_body": "Apple's event showcased the iPhone 15 lineup. Event stream: https://www.apple.com/apple-events Tech review images: iPhone15: https://images.apple.com/iphone15.jpg Blog coverage: www.techcrunch.com/apple-iphone-15 Summary: Improved battery life, new camera features, iOS 18 included. Emoji reaction: :smiling_face_with_heart-eyes::thumbs_up:",
            "clean_combined_withurl": "Apple announces new iPhone 15 release & pre-order starts soon 🍏. Apple announces new iPhone 15 release & pre-order starts soon :green_apple:. Apple's event showcased the iPhone 15 lineup. Event stream: Tech review images: iPhone15: Blog coverage: Summary: Improved battery life, new camera features, iOS 18 included. Emoji reaction: 😍👍",
            "clean_combined_withouturl": "Apple announces new iPhone 15 release & pre-order starts soon :green_apple:. Apple announces new iPhone 15 release & pre-order starts soon :green_apple:. Apple's event showcased the iPhone 15 lineup. Event stream: https://www.apple.com/apple-events Tech review images: iPhone15: https://images.apple.com/iphone15.jpg Blog coverage: www.techcrunch.com/apple-iphone-15 Summary: Improved battery life, new camera features, iOS 18 included. Emoji reaction: :smiling_face_with_heart-eyes::thumbs_up:"
        },
        "engagement": {
            "total_comments": 10, 
            "score": 45, 
            "upvote_ratio": 0.83
            }, 
        "metadata": {
            "subreddit": "wallstreetbets", 
            "category": ""
        }
    }

    result = service.preprocess_post(dummy_post)

    # Title cleaned
    assert result["content"]["clean_title"] == "Apple announces new iPhone 15 release & pre-order starts soon 🍏"

    # URLs
    assert "https://www.apple.com/apple-events" in result["links"]

    # Images
    assert "https://images.apple.com/iphone15.jpg" in result["images"]


    # Images removed in clean body
    assert "https://example.com" not in result["content"]["clean_combined_withouturl"]

    # Combined fields exist
    assert "clean_combined_withurl" in result["content"]
    assert "clean_combined_withouturl" in result["content"]

    # Emoji converted in combined_withouturl
    assert ":green_apple:" in result["content"]["clean_combined_withouturl"]


def test_image_extraction(service):
    post = {
        "content": {
            "title": "",
            "body": "Image here https://example.com/test.png"
        },
        "url": ""
    }

    result = service.preprocess_post(post)

    assert "https://example.com/test.png" in result["images"]


def test_link_extraction(service):
    post = {
        "content": {
            "title": "",
            "body": "Check https://example.com and http://test.com"
        },
        "url": ""
    }

    result = service.preprocess_post(post)

    assert "https://example.com" in result["links"]
    assert "http://test.com" in result["links"]


def test_empty_post(service):
    post = {}

    result = service.preprocess_post(post)
    assert result == None
