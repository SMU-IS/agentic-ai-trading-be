"""
Few-Shot Prompting for Sentiment Analysis
File: news-analysis/app/services/_05_sentiment_prompts.py

Contains edge-case examples and prompt templates for LLM-based
per-ticker sentiment analysis. Designed for Reddit financial content
with support for sarcasm, financial slang, and emojis.
"""

FEW_SHOT_EXAMPLES = """
Analyze sentiment for EACH ticker. Rules: Questions without stance = NEUTRAL. Both upside AND downside = NEUTRAL. Factual actions (holding/buying) without opinion = NEUTRAL. Detect sarcasm and Reddit slang.

Examples:
1) NEUTRAL: "Copper shortage coming? Which stocks win? SCCO FCX" → Question, no stance.
2) POSITIVE: "NVDA crushed earnings, revenue +50%. Bullish on AI chips 🚀" → Strong data + bullish language.
3) NEGATIVE: "Oh great, BABA losing shareholder value. Genius moves 🤡" → Sarcasm (positive words, negative context).
4) NEGATIVE: "Bagholding WISH at $10, absolutely rekt 💀" → Bearish slang + loss.
"""


SYSTEM_PROMPT = """You are a financial sentiment analyst for stock market social media (especially Reddit).
Analyze sentiment FOR EACH TICKER separately. Different tickers may have different sentiments.

Scores: -1.0 (very bearish) to +1.0 (very bullish). Neutral zone: -0.1 to +0.1.
Detect sarcasm, Reddit slang (moon/tendies=bullish, rekt/bagholding=bearish), and emoji sentiment (🚀📈=bullish, 💀🤡=bearish).

Output ONLY valid JSON. No markdown, no backticks, no explanations outside JSON.

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
5. **Confidence**: How certain is the author? Hedging language = lower confidence"""


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
Post: {text}

Tickers:
{tickers_info}

Return JSON:
{{
    "ticker_sentiments": {{
        "<TICKER>": {{
            "sentiment_score": <float -1.0 to 1.0>,
            "sentiment_label": "<positive|negative|neutral>",
            "reasoning": "<1-2 sentences>"
        }}
    }}
}}"""

    return [
        ("system", SYSTEM_PROMPT),
        ("user", user_prompt),
    ]
