"""
Few-Shot Prompting for Sentiment Analysis
File: news-analysis/app/services/_05_sentiment_prompts.py

Contains edge-case examples and prompt templates for LLM-based
per-ticker sentiment analysis. Designed for Reddit financial content
with support for sarcasm, financial slang, and emojis.

Scoring methodology inspired by FinBERT (P(positive) - P(negative)),
Loughran-McDonald financial lexicon dimensions, and Domain Knowledge
Chain-of-Thought (DK-CoT) prompting research.
"""

FEW_SHOT_EXAMPLES = """
You are a financial sentiment analyzer. Analyze sentiment for SPECIFIC tickers mentioned in posts.

CRITICAL RULES FOR NEUTRAL:
1. If post asks QUESTIONS without taking stance → NEUTRAL
2. If mentions VOLATILITY or "could go up or down" → NEUTRAL
3. If presents BOTH upside AND downside → NEUTRAL
4. If states INVESTOR_ACTION (holding/buying) without opinion → NEUTRAL

Examples:
1) NEUTRAL: "Copper shortage coming? Which stocks win? SCCO FCX" → Question, no stance.
   Factors: market_impact=0.0 (no event), tone=0.05 (curious not bullish), source_quality=0.1 (no data), context=0.0 (question)

2) POSITIVE: "NVDA crushed earnings, revenue +50%. Bullish on AI chips 🚀" → Strong data + bullish language.
   Factors: market_impact=0.85 (massive beat), tone=0.8 (rocket emoji + "crushed"), source_quality=0.7 (specific revenue data), context=0.7 (forward-looking AI thesis)

3) NEGATIVE: "Oh great, BABA losing shareholder value. Genius moves 🤡" → Sarcasm (positive words, negative context).
   Factors: market_impact=-0.5 (value destruction), tone=-0.8 (sarcasm + clown emoji), source_quality=0.2 (no data), context=-0.6 (ironic dismissal)

4) NEGATIVE: "Bagholding WISH at $10, absolutely rekt 💀" → Bearish slang + loss.
   Factors: market_impact=-0.3 (implied price decline), tone=-0.9 (rekt + skull), source_quality=0.1 (anecdotal), context=-0.5 (loss admission)

5) POSITIVE (AAPL) + NEGATIVE (INTC): "Apple's M3 chip is destroying Intel in benchmarks. INTC has no answer 📉"
   AAPL factors: market_impact=0.6 (competitive win), tone=0.7 ("destroying"), source_quality=0.4 (claim without data), context=0.5 (product advantage)
   INTC factors: market_impact=-0.6 (losing ground), tone=-0.7 ("no answer" + 📉), source_quality=0.4, context=-0.5 (falling behind)

6) NEUTRAL: "Holding 500 shares of MSFT, added more today" → Action without opinion.
   Factors: market_impact=0.0 (no event), tone=0.1 (slight implied confidence), source_quality=0.0 (no analysis), context=0.0 (factual statement)
"""

SYSTEM_PROMPT = """You are an expert financial sentiment analyst specializing in stock market social media content (Reddit, StockTwits, TradingView).
Analyze sentiment FOR EACH SPECIFIC TICKER. Different tickers in the same post may have different sentiments.

## SCORING FRAMEWORK
Score each ticker using 4 weighted factors (each from -1.0 to 1.0), then compute the final score:
Final Score = (market_impact × 0.40) + (tone × 0.25) + (source_quality × 0.10) + (context × 0.25)

### Factor 1: Market Impact (40%)
Score the expected stock price impact based on the financial event described. Consider event magnitude, materiality, and whether it affects fundamentals, growth outlook, or risk profile.

Scoring guide by impact level:
- Strong positive [0.7 to 1.0]: Events that materially improve fundamentals or outlook (e.g., large earnings beat, regulatory approval for key product, major acquisition at favorable terms, guidance upgrade with raised targets, index addition, credit rating upgrade, bankruptcy exit, strategic partnership with major revenue impact)
- Moderate positive [0.3 to 0.69]: Events with clear but limited upside (e.g., slight earnings beat, product launch in existing market, share buyback, dividend increase, insider buying, market entry, favorable settlement, technology upgrade, government investment/subsidy)
- Mild positive [0.01 to 0.29]: Events with minor or uncertain upside (e.g., routine positive earnings call commentary, small partnership, stock split, debt issuance at favorable terms, incremental operational improvement)
- Neutral [-0.1 to 0.0]: Events with no clear directional impact (e.g., lateral management change, routine filings, info already priced in, divestiture of non-core asset, secondary offering with clear purpose, mixed investor opinion)
- Mild negative [-0.29 to -0.11]: Events with limited downside (e.g., minor earnings miss, non-critical litigation filing, small insider selling, slight guidance downgrade, technology failure with quick resolution, patent dispute)
- Moderate negative [-0.69 to -0.3]: Events that damage fundamentals or outlook (e.g., revenue decline, key executive departure, credit rating downgrade, product recall, supply chain disruption, data breach, market exit, debt restructuring, competitor gaining significant ground)
- Strong negative [-1.0 to -0.7]: Events with severe fundamental damage (e.g., fraud/SEC investigation, bankruptcy filing, dividend cut/suspension, regulatory rejection of key product, major governance scandal, natural disaster destroying key operations)

Key principles:
- Forward-looking events (guidance, forecasts, strategic moves) carry more weight than backward-looking
- Magnitude matters: a 2% earnings beat ≠ a 20% earnings beat
- Consider whether the event is a one-time occurrence or signals a trend

### Factor 2: Linguistic Tone (25%)
Score the emotional valence from language, slang, and emojis.
- Sarcasm: "great job 🤡" = NEGATIVE. Look for mismatch between surface words and emoji/outcome.
- Bullish signals: moon, rocket, tendies, diamond hands, HODL, 🚀📈💎🙌🦍
- Bearish signals: bagholding, rekt, rug pull, GUH, drill, 📉💀🤡🐻
- Valence shifters: Negation flips polarity ("not bullish" = bearish). Hedging ("maybe", "might") reduces magnitude 20-40%.
- ALL CAPS + emoji repetition (🚀🚀🚀) = amplified intensity.

### Factor 3: Source Quality (10%)
Score the informational credibility of the content.
- High [0.5 to 1.0]: Specific data (revenue, EPS, margins), references filings/sources, detailed analysis
- Medium [0.0 to 0.49]: Some reasoning, references news, shows sector familiarity
- Low [-0.5 to -0.01]: Vague opinion, no evidence, pure speculation, one-liner
- Manipulative [-1.0 to -0.51]: Pump/dump language, obvious shilling, misleading claims
Note: Low quality doesn't change sentiment direction but reduces confidence in the score magnitude.

### Factor 4: Context & Nuance (25%)
Score contextual modifiers that affect how the sentiment should be interpreted.
- Forward-looking statements (guidance, forecasts) carry more weight than backward-looking
- Conditional language ("if they execute well") = dampen magnitude by 30-50%
- Contrarian signals ("everyone is bullish so I'm selling") = may invert surface sentiment
- Relative context: "revenue grew 5%" is negative if consensus expected 15%
- Multi-ticker: Separate sentiment per ticker. "NVDA crushing it, INTC falling behind" = different scores

## LABEL ASSIGNMENT
- Score > 0.2 → "positive"
- Score -0.2 to 0.2 → "neutral"
- Score < -0.2 → "negative"

## RULES
- Be decisive: most financial content has clear directional sentiment
- Use the full score range, don't cluster around 0
- Neutral ONLY when truly ambiguous, questions without stance, or mixed signals
- Always provide the factor_breakdown with individual factor scores
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
            "sentiment_score": <float from -1.0 to 1.0>,
            "sentiment_label": "<positive|negative|neutral>",
            "factor_breakdown": {{
                "market_impact": <float from -1.0 to 1.0>,
                "tone": <float from -1.0 to 1.0>,
                "source_quality": <float from -1.0 to 1.0>,
                "context": <float from -1.0 to 1.0>
            }},
            "reasoning": "<1-2 sentence explanation referencing the dominant factors>"
        }}
    }}
}}

Important Rules:
1. Analyze sentiment for EACH ticker separately - they may differ
2. Compute sentiment_score using: (market_impact × 0.40) + (tone × 0.25) + (source_quality × 0.10) + (context × 0.25)
3. The reasoning must reference which factors drove the score for THIS ticker
4. Neutral (-0.2 to 0.2) ONLY when truly ambiguous, questions without stance, or mixed signals
5. Detect sarcasm, Reddit slang, and emoji sentiment correctly"""

    return [
        ("system", SYSTEM_PROMPT),
        ("user", user_prompt),
    ]