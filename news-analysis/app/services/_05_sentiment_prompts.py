"""
Few-Shot Prompting for Sentiment Analysis
File: news-analysis/app/services/_05_sentiment_prompts.py

Contains edge-case examples and prompt templates for LLM-based
per-ticker sentiment analysis. Designed for Reddit financial content
with support for sarcasm, financial slang, and emojis.
"""

FEW_SHOT_EXAMPLES = """
You are a financial sentiment analyzer. Analyze sentiment for SPECIFIC tickers mentioned in posts.

CRITICAL RULES FOR NEUTRAL:
1. If post asks QUESTIONS without taking stance → NEUTRAL
2. If mentions VOLATILITY or "could go up or down" → NEUTRAL
3. If presents BOTH upside AND downside → NEUTRAL
4. If states INVESTOR_ACTION (holding/buying) without opinion → NEUTRAL

Examples:
Examples:
1) NEUTRAL: "Copper shortage coming? Which stocks win? SCCO FCX" → Question, no stance.
2) POSITIVE: "NVDA crushed earnings, revenue +50%. Bullish on AI chips 🚀" → Strong data + bullish language.
3) NEGATIVE: "Oh great, BABA losing shareholder value. Genius moves 🤡" → Sarcasm (positive words, negative context).
4) NEGATIVE: "Bagholding WISH at $10, absolutely rekt 💀" → Bearish slang + loss.
"""

SYSTEM_PROMPT = """You are an expert financial sentiment analyst specializing in stock market news and social media content analysis (especially Reddit posts).
Your task is to analyze the sentiment of financial content FOR EACH SPECIFIC TICKER mentioned.
Different tickers in the same post may have different sentiments.

## Sentiment Score Guidelines
- Score range: -1.0 (extremely bearish) to +1.0 (extremely bullish)
- Neutral zone: -0.1 to +0.1 (use when sentiment is truly ambiguous, factual, or mixed)
- Be decisive: Most financial content has clear directional sentiment

## Score Interpretation
| Score Range | Label | Meaning |
|-------------|-------|---------|
| +0.7 to +1.0 | positive | Strongly bullish - major positive catalyst, exceptional news |
| +0.3 to +0.69 | positive | Moderately bullish - positive developments, optimistic outlook |
| +0.1 to +0.29 | positive | Slightly bullish - mild positive sentiment, cautious optimism |
| -0.1 to +0.1 | neutral | Neutral - factual reporting, questions, mixed signals, no clear bias |
| -0.29 to -0.1 | negative | Slightly bearish - mild concerns, cautious pessimism |
| -0.69 to -0.3 | negative | Moderately bearish - negative developments, pessimistic outlook |
| -1.0 to -0.7 | negative | Strongly bearish - major negative catalyst, crisis/disaster |

## Reddit & Social Media Analysis
1. **Sarcasm Detection**: "great job losing money" is NEGATIVE despite "great". Look for mismatched tone and outcome.
2. **Financial Slang**: Bullish = moon, rocket, tendies, diamond hands, YOLO, ape strong. Bearish = bagholding, rekt, GG, drill, cliff, rug pull.
3. **Emojis**: Bullish = 🚀📈💎🔥🦍. Bearish = 📉💀🤡⚠️🐻. Consider emoji clusters for emphasis.
4. **WSB Culture**: Understand ironic self-deprecation vs genuine sentiment. "Loss porn" posts are bearish on the ticker.

## Analysis Factors
1. **Direct Impact**: How does the content affect the company's fundamentals?
2. **Market Context**: Consider sector trends, competitive dynamics
3. **Language Tone**: Explicit bullish/bearish language and modifiers
4. **Event Type**: Earnings beat/miss, M&A, FDA approval/rejection, legal issues
5. **Confidence**: How certain is the author? Hedging language = lower confidence

Output ONLY valid JSON. No markdown, no explanations outside JSON."""


def build_sentiment_prompt(text: str, tickers_info: str) -> list:
    """
    Build few-shot prompt messages for sentiment analysis.

    Args:
        text: The cleaned post/news content (clean_combined_withurl)
        tickers_info: Formatted ticker info string from ticker_metadata

    Returns:
        List of message tuples for ChatPromptTemplate
    """
    user_prompt = FEW_SHOT_EXAMPLES + f"""

Now analyze this post:

Post: {text}

Tickers to Analyze:
{tickers_info}

Return ONLY valid JSON (no markdown, no backticks):
{{
    "ticker_sentiments": {{
        "<TICKER_SYMBOL>": {{
            "sentiment_score": <float from -1.0 to 1.0>,
            "sentiment_label": "<positive|negative|neutral>",
            "reasoning": "<1-2 sentence explanation of WHY this sentiment for THIS specific ticker>"
        }}
    }}
}}

Important Rules:
1. Analyze sentiment for EACH ticker separately - they may differ
2. The reasoning must explain why THIS ticker has THIS sentiment based on the content
3. Use the full score range - don't cluster around 0
4. Neutral (-0.1 to 0.1) ONLY when truly ambiguous, questions without stance, or mixed signals
5. Detect sarcasm, Reddit slang, and emoji sentiment correctly"""

    return [
        ("system", SYSTEM_PROMPT),
        ("user", user_prompt),
    ]
