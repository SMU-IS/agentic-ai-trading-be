# FinBERT sentiment scoring logic
from typing import Dict, List
import re
import numpy as np

from transformers import pipeline
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


class SentimentAnalyzer:
    TICKER_REGEX = re.compile(r"\$[A-Z]{1,5}")
    FINBERT_WEIGHT = 0.65
    VADER_WEIGHT = 0.35

    def __init__(self, finbert_model: str = "ProsusAI/finbert"):
        # Initialize analyzers
        self.finbert = pipeline(
            "sentiment-analysis",
            model=finbert_model,
            return_all_scores=True
        )
        self.vader = SentimentIntensityAnalyzer()

    # Relevance and ticker extraction
    def extract_tickers(self, text: str) -> List[str]:
        tickers = self.TICKER_REGEX.findall(text)
        return list(set(t.replace("$", "") for t in tickers))

    def is_relevant(self, text: str) -> bool:
        return len(self.extract_tickers(text)) > 0

    # FinBERT sentiment analysis
    def finbert_sentiment(self, text: str) -> Dict:
        results = self.finbert(text)[0]

        label_map = {
            "positive": 1,
            "neutral": 0,
            "negative": -1
        }

        score = 0.0
        confidence = 0.0
        label = "neutral"

        for r in results:
            score += label_map[r["label"]] * r["score"]
            if r["score"] > confidence:
                confidence = r["score"]
                label = r["label"]

        return {
            "score": score,
            "label": label,
            "confidence": confidence
        }

    # VADER sentiment analysis
    def vader_sentiment(self, text: str) -> Dict:
        scores = self.vader.polarity_scores(text)
        compound = scores["compound"]

        if compound >= 0.05:
            label = "positive"
        elif compound <= -0.05:
            label = "negative"
        else:
            label = "neutral"

        return {
            "score": compound,
            "label": label,
            "confidence": abs(compound)
        }

    # Combined sentiment analysis
    def combined_sentiment(self, finbert_res: Dict, vader_res: Dict) -> Dict:
        final_score = (
            self.FINBERT_WEIGHT * finbert_res["score"]
            + self.VADER_WEIGHT * vader_res["score"]
        )

        confidence = np.mean([
            finbert_res["confidence"],
            vader_res["confidence"]
        ])

        if final_score > 0.05:
            label = "positive"
        elif final_score < -0.05:
            label = "negative"
        else:
            label = "neutral"

        return {
            "score": final_score,
            "label": label,
            "confidence": confidence
        }

    def process(self, data: Dict) -> Dict:
        text = data["clean_combined"]

        if not self.is_relevant(text):
            return data

        finbert_res = self.finbert_sentiment(text)
        vader_res = self.vader_sentiment(text)
        combined = self.combined_sentiment(finbert_res, vader_res)

        return {
            "Post_ID": data.get("Post_ID"),
            "Post_URL": data.get("Post_URL"),
            "Author": data.get("Author"),
            "Timestamp_UTC": data.get("Timestamp_UTC"),
            "Timestamp_ISO": data.get("Timestamp_ISO"),
            "Total_Comments": data.get("Total_Comments"),
            "Score": data.get("Score"),
            "Upvote_Ratio": data.get("Upvote_Ratio"),
            "Subreddit": data.get("Subreddit"),
            "Domain": data.get("Domain"),
            "urls": data.get("urls"),
            "images": data.get("images"),
            "raw_title": data.get("raw_title"),
            "raw_body": data.get("raw_body"),
            "clean_title": data.get("clean_title"),
            "clean_body": data.get("clean_body"),
            "clean_combined": data.get("clean_combined"),
            "sentiment_score": combined["score"],
            "sentiment_label": combined["label"],
            "confidence": combined["confidence"],
            "models_used": ["FinBERT", "VADER"]
        }