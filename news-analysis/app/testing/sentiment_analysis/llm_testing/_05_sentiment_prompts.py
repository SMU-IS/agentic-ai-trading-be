"""
Few-Shot Prompting for Sentiment Analysis
File: news-analysis/app/testing/sentiment_analysis/llm_testing/_05_sentiment_prompts.py

Contains edge-case examples and prompt templates for LLM-based
per-ticker sentiment analysis. Designed for Reddit financial content
with support for sarcasm, financial slang, and emojis.

Scoring methodology inspired by FinBERT (P(positive) - P(negative)),
Loughran-McDonald financial lexicon dimensions, and Domain Knowledge
Chain-of-Thought (DK-CoT) prompting research.
"""

FEW_SHOT_EXAMPLES = """
Analyze sentiment for SPECIFIC tickers. NEUTRAL only for questions without stance, mixed signals, or actions without opinion.

Examples:
1) NEUTRAL: "Holding 500 shares of MSFT, added more today" → Action without opinion.
   Scoring: market_impact=0.0, tone=0.1, source_quality=0.0, context=0.0
   Reasoning: Factual action statement; no bullish or bearish stance expressed.

2) POSITIVE: "NVDA crushed earnings, revenue +50%. Bullish on AI chips 🚀" → Strong data + bullish language.
   Scoring: market_impact=0.85, tone=0.8, source_quality=0.7, context=0.7
   Reasoning: Large earnings beat with hard data; rocket emoji and "crushed" amplify bullish tone.

3) NEGATIVE: "Oh great, BABA losing shareholder value. Genius moves 🤡" → Sarcasm detection.
   Scoring: market_impact=-0.5, tone=-0.8, source_quality=0.2, context=-0.6
   Reasoning: Sarcastic praise + clown emoji signals negative tone despite positive surface words.

4) POSITIVE (AAPL) + NEGATIVE (INTC): "Apple's M3 chip is destroying Intel in benchmarks. INTC has no answer 📉"
   AAPL: market_impact=0.6, tone=0.7, source_quality=0.4, context=0.5
   INTC: market_impact=-0.6, tone=-0.7, source_quality=0.4, context=-0.5
   Reasoning: Competitive win lifts AAPL; same event is a direct loss for INTC confirmed by 📉.
"""

SYSTEM_PROMPT = """You are a financial sentiment analyst for stock market social media (Reddit, StockTwits).
Analyze sentiment FOR EACH SPECIFIC TICKER separately — different tickers in the same post may have different sentiments.

## SCORING
Final Score = (market_impact × 0.40) + (tone × 0.25) + (source_quality × 0.20) + (context × 0.15)
Each factor: -1.0 to 1.0. Forward-looking events carry more weight than backward-looking. Magnitude matters.

### Factor 1: Market Impact (40%)
Expected stock price impact from the financial event described.
- Strong positive [0.7–1.0]: Major earnings beat, regulatory approval, guidance upgrade, index addition, credit upgrade
- Moderate positive [0.4–0.69]: Slight earnings beat, buyback, dividend increase, favorable settlement, subsidy
- Mild positive [0.2–0.39]: Minor partnership, stock split, incremental improvement
- Neutral [-0.19–0.19]: Lateral management change, routine filings, already-priced-in news
- Mild negative [-0.39–-0.2]: Minor miss, small insider sell, slight guidance cut, patent dispute
- Moderate negative [-0.69–-0.4]: Revenue decline, key exec departure, product recall, data breach, credit downgrade
- Strong negative [-1.0–-0.7]: Fraud/SEC investigation, bankruptcy, dividend cut, major scandal

### Factor 2: Linguistic Tone (25%)
Emotional valence from language, slang, emojis.
- Bullish: moon, rocket, tendies, diamond hands, HODL, 🚀📈💎🙌🦍
- Bearish: bagholding, rekt, rug pull, GUH, 📉💀🤡🐻
- Sarcasm: positive words + negative emoji/outcome = NEGATIVE
- Negation flips polarity; hedging reduces magnitude 20–40%; ALL CAPS/emoji repeats amplify intensity

### Factor 3: Source Quality (20%)
- High [0.5–1.0]: Specific data (EPS, revenue, margins), references filings
- Medium [0.0–0.49]: Some reasoning, references news
- Low [-0.5–-0.01]: Vague opinion, speculation, one-liner
- Manipulative [-1.0–-0.51]: Pump/dump, shilling, misleading claims

### Factor 4: Context & Nuance (15%)
- Conditional language ("if they execute") dampens magnitude 30–50%
- Contrarian signals may invert surface sentiment
- Relative context: "grew 5%" is negative if consensus was 15%

## LABELS: score > 0.2 → positive | -0.2 to 0.2 → neutral | score < -0.2 → negative

## RULES
- Be decisive; use the full score range; neutral only when truly ambiguous
- Output ONLY valid JSON. No markdown, no explanations outside JSON."""


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
            "sentiment_score": <float -1.0 to 1.0>,
            "sentiment_label": "<positive|negative|neutral>",
            "factor_breakdown": {{
                "market_impact": <float -1.0 to 1.0>,
                "tone": <float -1.0 to 1.0>,
                "source_quality": <float -1.0 to 1.0>,
                "context": <float -1.0 to 1.0>
            }},
            "reasoning": "<1-2 sentences referencing dominant factors>"
        }}
    }}
}}"""

    return [
        ("system", SYSTEM_PROMPT),
        ("user", user_prompt),
    ]