import html
import re
import unicodedata
from typing import Dict
import string
import emoji
import ftfy
import strip_markdown


class PreprocessingService:
    """
    Preprocesses scraped posts and removes multispace, control characters and markdown. 
    Preserves casing, symbols, numbers, punctuation, and emoji description for downstream analysis.
    """

    def __init__(self):
        self.URL_PATTERN = re.compile(r"(https?://\S+|www\.\S+)", flags=re.IGNORECASE)
        self.MARKDOWN_URL_PATTERN = re.compile(
            r"!?\[([^\]]+)\]\((https?://\S+|www\.\S+)\)", flags=re.IGNORECASE
        )
        self.UNICODE_PUNCT_MAP = str.maketrans({
            "—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'"
        })
        self.MULTI_WHITESPACE = re.compile(r"\s+")
        self.CONTROL_CHARS = re.compile(r"[\r\n\t]+")
        self.IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp"]
        exts = "|".join(self.IMAGE_EXTENSIONS)
        self.IMAGE_PATTERN = re.compile(
            r"(https?://\S+\.(?:%s)|www\.\S+\.(?:%s))" % (exts, exts),
            flags=re.IGNORECASE,
        )

    def clean_text(self, text: str, remove_urls: bool = False) -> str:
        if not text:
            return ""

        text = html.unescape(text)
        text = text.replace('\\"', '"')
        text = ftfy.fix_text(text)
        text = unicodedata.normalize("NFKC", text)
        text = text.translate(self.UNICODE_PUNCT_MAP)

        if remove_urls:
            # Remove Markdown links entirely (anchor + URL)
            text = self.MARKDOWN_URL_PATTERN.sub("", text)
            # Remove raw URLs
            text = self.URL_PATTERN.sub("", text)
        else:
            # Keep anchor text and URL in the form "anchor_text: URL"
            text = self.MARKDOWN_URL_PATTERN.sub(r"\1: \2", text)

        # Remove remaining Markdown syntax
        text = strip_markdown.strip_markdown(text)
        
        # Replace control characters and normalize spaces
        text = self.CONTROL_CHARS.sub(" ", text)
        text = self.MULTI_WHITESPACE.sub(" ", text).strip()

        return text

    def preprocess_post(self, post: Dict) -> Dict:
        """Processes a single post, returns cleaned text with metadata."""
        if post:
            raw_title = post.get("content", {}).get("title", "")
            raw_body  = post.get("content", {}).get("body", "")
            post_url = post.get("url")

            # Extract URLs and images
            urls = self.URL_PATTERN.findall(raw_title) + self.URL_PATTERN.findall(raw_body)
            images = (
                self.IMAGE_PATTERN.findall(raw_title)
                + self.IMAGE_PATTERN.findall(raw_body)
                + self.IMAGE_PATTERN.findall(post_url or "")
            )
            urls = [url.rstrip(".,)]+") for url in urls]
            images = [url.rstrip(".,)]+") for url in images]
            # Remove URLs that are also in images
            urls = [url for url in urls if url not in images]

            # Clean text
            clean_title = self.clean_text(raw_title) 
            clean_body_withurl = self.clean_text(raw_body, remove_urls=False)
            clean_body_withouturl = self.clean_text(raw_body, remove_urls=True)
            separator = ""
            if clean_title:
                separator = " " if clean_title[-1] in string.punctuation else ". "
            
            clean_combined_withurl = f"{clean_title}{separator}{clean_body_withurl}".strip()
            clean_combined_withouturl = f"{clean_title}{separator}{clean_body_withouturl}".strip()
            clean_combined_withouturl = emoji.demojize(clean_combined_withouturl)
            post["content"]["clean_title"] = clean_title
            post["content"]["clean_body"] = clean_body_withurl
            post["content"]["clean_combined_withurl"] = clean_combined_withurl
            post["content"]["clean_combined_withouturl"] = clean_combined_withouturl
            post["images"] = images
            post["links"] = urls

            return post
        else:
            return None
