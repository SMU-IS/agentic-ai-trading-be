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
            "body": "Ａpple's event showcased the iPhone 15 lineup.\n\nEvent stream: https://www.apple.com/apple-events\nTech review images: ![iPhone15](https://images.apple.com/iphone15.jpg)\nBlog coverage: www.techcrunch.com/apple-iphone-15\nSummary: <b>Improved battery life</b>, new camera features, iOS 18 included.\nEmoji reaction: 😍👍",
        },
        "engagement": {"total_comments": 10, "score": 45, "upvote_ratio": 0.83},
        "metadata": {"subreddit": "wallstreetbets", "category": ""},
    }

    result = service.preprocess_post(dummy_post)

    # Title cleaned — fullwidth "Ａ" normalized, emoji preserved
    assert result["content"]["clean_title"] == "Apple announces new iPhone 15 release & pre-order starts soon 🍏"

    # Links extracted (non-image URLs only)
    assert "https://www.apple.com/apple-events" in result["links"]
    assert "www.techcrunch.com/apple-iphone-15" in result["links"]

    # Images extracted
    assert "https://images.apple.com/iphone15.jpg" in result["images"]
    assert "https://i.redd.it/4w98jvn7jlmg1.jpeg" in result["images"]

    # Image URLs not in links
    assert "https://images.apple.com/iphone15.jpg" not in result["links"]

    # Combined fields exist
    assert "clean_combined_withurl" in result["content"]
    assert "clean_combined_withouturl" in result["content"]

    # withurl keeps URLs
    assert "https://www.apple.com/apple-events" in result["content"]["clean_combined_withurl"]

    # withouturl removes URLs
    assert "https://www.apple.com/apple-events" not in result["content"]["clean_combined_withouturl"]

    # Emoji demojized only in withouturl
    assert ":green_apple:" in result["content"]["clean_combined_withouturl"]
    assert "🍏" in result["content"]["clean_combined_withurl"]


def test_image_extraction(service):
    post = {
        "content": {"title": "", "body": "Image here https://example.com/test.png"},
        "url": "",
    }

    result = service.preprocess_post(post)

    assert "https://example.com/test.png" in result["images"]


def test_link_extraction(service):
    post = {
        "content": {
            "title": "",
            "body": "Check https://example.com and http://test.com",
        },
        "url": "",
    }

    result = service.preprocess_post(post)

    assert "https://example.com" in result["links"]
    assert "http://test.com" in result["links"]


def test_image_not_in_links(service):
    post = {
        "content": {
            "title": "",
            "body": "See https://example.com/photo.jpg and https://example.com/page",
        },
        "url": "",
    }

    result = service.preprocess_post(post)

    assert "https://example.com/photo.jpg" in result["images"]
    assert "https://example.com/photo.jpg" not in result["links"]
    assert "https://example.com/page" in result["links"]


def test_withurl_keeps_urls_withouturl_removes(service):
    post = {
        "content": {
            "title": "Breaking news",
            "body": "Read more at https://example.com/article",
        },
        "url": "",
    }

    result = service.preprocess_post(post)

    assert "https://example.com/article" in result["content"]["clean_combined_withurl"]
    assert "https://example.com/article" not in result["content"]["clean_combined_withouturl"]


def test_emoji_demojized_only_in_withouturl(service):
    post = {
        "content": {
            "title": "Stock up 🚀",
            "body": "Huge gains today 💰",
        },
        "url": "",
    }

    result = service.preprocess_post(post)

    assert ":rocket:" in result["content"]["clean_combined_withouturl"]
    assert ":money_bag:" in result["content"]["clean_combined_withouturl"]
    assert "🚀" in result["content"]["clean_combined_withurl"]
    assert "💰" in result["content"]["clean_combined_withurl"]


def test_empty_post(service):
    post = {}

    result = service.preprocess_post(post)
    assert result is None
