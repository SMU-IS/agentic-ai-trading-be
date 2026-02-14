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

Example 1 - NEUTRAL (Question without stance):
Post: "I heard there is a copper supply shortage. When will this officially happen and which companies will win? SCCO FCX TECK"
Event: SUPPLY_CHAIN_DISRUPTION
Ticker: SCCO
Sentiment: NEUTRAL
Reasoning: Post asks questions ("when will this happen", "which companies") without providing directional opinion or stance.

Example 2 - NEUTRAL (Volatility, both sides):
Post: "AAPL is very volatile right now. Could go up after earnings or crash if they miss. Hard to say."
Event: EARNINGS_REPORT
Ticker: AAPL
Sentiment: NEUTRAL
Reasoning: Explicitly mentions both upside ("go up") and downside ("crash"), presents no clear direction.

Example 3 - NEUTRAL (INVESTOR_ACTION - factual):
Post: "I'm holding TSLA long term. Added more shares at $200."
Event: INVESTOR_ACTION
Ticker: TSLA
Sentiment: NEUTRAL
Reasoning: This is a FACTUAL statement of position (holding, buying), not an OPINION about TSLA's prospects.

Example 4 - POSITIVE (Clear positive with data):
Post: "NVDA crushed earnings! Revenue up 50% YoY, margins expanding. Bullish on AI chips."
Event: EARNINGS_REPORT
Ticker: NVDA
Sentiment: POSITIVE
Reasoning: Strong positive language ("crushed"), concrete positive data (50% growth), explicit bullish stance.

Example 5 - NEGATIVE (Clear negative):
Post: "UBER losing market share to Lyft. Terrible quarter, revenue missed estimates badly."
Event: EARNINGS_REPORT
Ticker: UBER
Sentiment: NEGATIVE
Reasoning: Negative outcomes (losing share, missed estimates), critical language ("terrible").

Example 6 - NEUTRAL (INVESTOR_OPINION but speculative):
Post: "I think GOOGL might do well OR might struggle with AI competition. Too early to tell."
Event: INVESTOR_OPINION
Ticker: GOOGL
Sentiment: NEUTRAL
Reasoning: Even though it's labeled OPINION, the post hedges both ways ("might do well OR might struggle"), no clear position.

Example 7 - POSITIVE (Clear despite event type):
Post: "I'm extremely bullish on MSFT. Cloud growth is unstoppable, buying more shares."
Event: INVESTOR_OPINION
Ticker: MSFT
Sentiment: POSITIVE
Reasoning: Clear positive opinion ("extremely bullish", "unstoppable"), actionable stance (buying).

Example 8 - POSITIVE (Reddit slang / sarcasm):
Post: "NVDA to the moon 🚀🚀🚀 diamond hands baby! Tendies incoming! This ape isn't selling."
Event: INVESTOR_OPINION
Ticker: NVDA
Sentiment: POSITIVE
Reasoning: Reddit/WSB bullish slang ("to the moon", "diamond hands", "tendies"), rocket emojis, strong conviction language.

Example 9 - NEGATIVE (Sarcasm detection):
Post: "Oh great, BABA management doing a fantastic job losing shareholder value. Really genius moves. 🤡🤡"
Event: CORPORATE_GOVERNANCE
Ticker: BABA
Sentiment: NEGATIVE
Reasoning: Sarcastic use of positive words ("great", "fantastic", "genius") with negative context (losing value), clown emojis confirm negative intent.

Example 10 - NEGATIVE (Reddit slang bearish):
Post: "Bagholding WISH at $10 avg, this stock is absolutely rekt. GG my portfolio 💀"
Event: INVESTOR_ACTION
Ticker: WISH
Sentiment: NEGATIVE
Reasoning: Bearish Reddit slang ("bagholding", "rekt", "GG"), skull emoji, implies significant unrealized losses.
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
{{{{
    "ticker_sentiments": {{{{
        "<TICKER_SYMBOL>": {{{{
            "sentiment_score": <float from -1.0 to 1.0>,
            "sentiment_label": "<positive|negative|neutral>",
            "reasoning": "<1-2 sentence explanation of WHY this sentiment for THIS specific ticker>"
        }}}}
    }}}}
}}}}

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


# Structured examples for programmatic access
NEUTRAL_EXAMPLES = [
    {
        "post": "Copper shortage coming? Which stocks will benefit? SCCO FCX",
        "ticker": "SCCO",
        "event": "SUPPLY_CHAIN_DISRUPTION",
        "label": "neutral",
        "reason": "Asks question without stance"
    },
    {
        "post": "AAPL volatile, could go up or down after earnings",
        "ticker": "AAPL",
        "event": "EARNINGS_REPORT",
        "label": "neutral",
        "reason": "Presents both upside and downside"
    },
    {
        "post": "I'm holding TSLA long term",
        "ticker": "TSLA",
        "event": "INVESTOR_ACTION",
        "label": "neutral",
        "reason": "Factual position statement, not opinion"
    }
]

POSITIVE_EXAMPLES = [
    {
        "post": "NVDA crushed earnings! Revenue up 50%, very bullish",
        "ticker": "NVDA",
        "event": "EARNINGS_REPORT",
        "label": "positive",
        "reason": "Strong positive data and language"
    },
    {
        "post": "NVDA to the moon diamond hands baby! Tendies incoming!",
        "ticker": "NVDA",
        "event": "INVESTOR_OPINION",
        "label": "positive",
        "reason": "Reddit bullish slang and rocket emojis"
    }
]

NEGATIVE_EXAMPLES = [
    {
        "post": "UBER terrible quarter, revenue missed badly",
        "ticker": "UBER",
        "event": "EARNINGS_REPORT",
        "label": "negative",
        "reason": "Negative outcomes and critical language"
    },
    {
        "post": "Oh great, BABA management doing a fantastic job losing shareholder value. Really genius moves.",
        "ticker": "BABA",
        "event": "CORPORATE_GOVERNANCE",
        "label": "negative",
        "reason": "Sarcastic positive words with negative context"
    }
]
