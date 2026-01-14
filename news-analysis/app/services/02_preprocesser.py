import html
import re
import unicodedata
from datetime import datetime
from typing import Dict, List, Union

import emoji
import ftfy
import strip_markdown


class PreprocessingService:
    """
    Preprocesses scraped posts and removes multispace, control characters, markdown and emojis (converted into :emoji:)
    Preserves casing, symbols, numbers, punctuation and emoji description for downstream analysis
    """

    def __init__(self):
        self.URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+)", flags=re.IGNORECASE)
        self.MARKDOWN_URL_PATTERN = re.compile(
            r"!?\[([^\]]+)\]\((https?://\S+|www\.\S+)\)", flags=re.IGNORECASE
        )
        self.MULTI_WHITESPACE = re.compile(r"\s+")
        self.CONTROL_CHARS = re.compile(r"[\r\n\t]+")
        self.IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp"]
        exts = "|".join(self.IMAGE_EXTENSIONS)
        self.IMAGE_PATTERN = re.compile(
            r"(https?://\S+\.(?:%s)|www\.\S+\.(?:%s))" % (exts, exts),
            flags=re.IGNORECASE,
        )

    # Cleaning text
    def clean_text(self, text: str) -> str:
        if not text:
            return ""

        text = html.unescape(text)
        text = ftfy.fix_text(text)
        text = unicodedata.normalize("NFKC", text)
        text = self.MARKDOWN_URL_PATTERN.sub(r"\1: \2", text)
        text = strip_markdown.strip_markdown(text)
        # converts emoji to text e.g. 😍 -> :heart_eyes:
        text = emoji.demojize(text)
        text = self.CONTROL_CHARS.sub(" ", text)
        text = self.MULTI_WHITESPACE.sub(" ", text).strip()

        return text

    # Convert datetime to ISO format (human readable)
    def convert_datetime_iso(self, ts):
        if ts is None:
            return None
        try:
            if isinstance(ts, str) and ts.isdigit():
                ts = int(ts)
            if isinstance(ts, (int, float)):
                return datetime.utcfromtimestamp(ts).isoformat()
            dt = datetime.fromisoformat(ts)
            return dt.isoformat()
        except Exception:
            return None

    # Preprocessing each post
    def preprocess_post(self, post: Dict) -> Dict:
        raw_title = post.get("Title", "")
        raw_body = post.get("Body", "")
        urls = self.URL_PATTERN.findall(raw_title) + self.URL_PATTERN.findall(raw_body)
        images = self.IMAGE_PATTERN.findall(raw_title) + self.IMAGE_PATTERN.findall(
            raw_body
        )
        urls = [url.rstrip(".,)]+") for url in urls]
        images = [url.rstrip(".,)]+") for url in images]
        # Remove URLs that are also in images
        urls = [url for url in urls if url not in images]
        clean_title = self.clean_text(raw_title)
        clean_body = self.clean_text(raw_body)
        timestamp = post.get("Timestamp_UTC")

        return {
            "Post_ID": post.get("Post_ID"),
            "Post_URL": post.get("Post_URL"),
            "Author": post.get("Author"),
            "Timestamp_UTC": timestamp,
            "Timestamp_ISO": self.convert_datetime_iso(timestamp),
            "Total_Comments": post.get("Total_Comments"),
            "Score": post.get("Score"),
            "Upvote_Ratio": post.get("Upvote_Ratio"),
            "Subreddit": post.get("Subreddit"),
            "Domain": post.get("Domain"),
            "urls": urls,
            "images": images,
            "raw_title": raw_title,
            "raw_body": raw_body,
            "clean_title": clean_title,
            "clean_body": clean_body,
            "clean_combined": f"{clean_title}. {clean_body}".strip(),
        }

    # Process Post Input: Must be a dict or a list of dict
    def process_input(self, data: Union[List[Dict], Dict]) -> Union[List[Dict], Dict]:
        if isinstance(data, list):
            return [self.preprocess_post(post) for post in data]
        if isinstance(data, dict):
            return self.preprocess_post(data)
        raise TypeError("Input must be a dict or list of dicts")
