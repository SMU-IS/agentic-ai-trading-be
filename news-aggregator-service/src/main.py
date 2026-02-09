import asyncio
import os
# from src.services.redis_service import RedisService
from src.services.llm_service import LLMService
# from src.workflows.main_workflow import app
from src.config import settings

from dotenv import load_dotenv
load_dotenv()

# async def main():
#     # Initialize services
#     redis_service = RedisService()
#     llm_service = LLMService(os.getenv("OPENAI_API_KEY"))
    
#     await redis_service.connect()
    
#     print("🚀 News Aggregator started...")
    
#     async for article in redis_service.listen_news_stream():
#         # Process batch of articles
#         result = await app.ainvoke({
#             "articles": [article.model_dump()],
#             "topics": [],
#             "triggered_topics": [],
#             "analyses": [],
#             "signals": []
#         })
        
#         if result["signals"]:
#             print(f"📡 Generated {len(result['signals'])} signals")
    
#     await redis_service.close()
import time 

## prompt v1
# system_prompt = """
# You are a financial fact-checker and swing trade evaluator specializing in speculative stocks (penny stocks, low-float tickers). Analyze rumors from forums/social media (Reddit, X, StockTwits) for credibility and trade potential. Use only the provided rumor/context—no external tools or searches.

# RUMOR TO EVALUATE: {insert_rumor_here}
# TICKER: {insert_ticker_here}
# CURRENT DATE: {insert_date_here}
# ADDITIONAL CONTEXT: {insert_any_prior_info_here e.g. price surge details}

# Step-by-step evaluation:

# 1. **Source Hierarchy & Specificity**:
# - Identify rumor sources (forum posts? screenshots? links?).
# - Rate specificity (1-10): Vague hype=1, named insiders/dates/filings=10.
# - Check against hierarchies: Official (SEC/PR)=High, Media=Med, Social=Low.

# 2. **Cross-Verification**:
# - Earnings/Financials: Confirm via known calendars/filings? Red flag if unfiled.
# - Insider Activity: Specific Form 4 details? General claims=weak.
# - Other Catalysts: Partnerships/contracts need PR proof.
# - Materiality: Matches price/volume surge? (±3 days).

# 3. **Credibility Score** (Low/Medium/High):
# - Low: Forum-only, no primaries, denied/missing.
# - Medium: Multi-forum buzz + surge, no denial.
# - High: Official confirmation (filing/PR).

# 4. **Swing Trade Assessment** (2-10 day hold, 10-30% target):
# - Catalyst Strength: High=Buy signal if technicals align.
# - Technicals: Assume volume 3x+, breakout? (Flag if data provided).
# - Risk-Reward: Position 1% portfolio, stop -8%, exit on denial/news.
# - Decision: Buy (strong), Watch (partial), No (weak/high risk).

# Output ONLY valid JSON, no extra text:

# {
# "ticker": "{ticker}",
# "rumor_summary": "1-sentence rumor recap",
# "credibility": "Low|Medium|High",
# "credibility_reason": "2-3 sentences explaining score",
# "trade_opportunity": "Buy|Short|Watch|No",
# "trade_rationale": "Key factors (catalyst, risk, setup)",
# "confidence": 1-10,
# "recommended_actions": ["e.g. Monitor volume", "Avoid until filing", "Long if >5x vol"]
# }
# """

system_prompt = """
You are a financial fact-checker and swing trade evaluator specializing in speculative stocks. Analyze rumors from forums/social media for credibility and **extreme trade signals only**. Output Buy/Short/NO TRADE—NO passive actions like "watch" or "monitor."

RUMOR TO EVALUATE: {insert_rumor_here}
TICKER: {insert_ticker_here}
CURRENT DATE: {insert_date_here}
ADDITIONAL CONTEXT: {insert_any_prior_info_here}

Step-by-step evaluation (reason explicitly):

1. **Source Hierarchy & Specificity** (1-10):
   - Official (SEC/PR/IR)=High, Media=Med, Social/Forums=Low
   - Vague hype=1, specific filings/names/dates=10

2. **Cross-Verification**:
   - Earnings: Filed 10-Q/8-K? Calendar match?
   - Insiders: Form 4 with names/shares?
   - Materiality: 3x+ volume + price spike alignment?

3. **Credibility**: Low/Medium/High (Low=forums only)

4. **TRADE SIGNAL** (EXTREME ONLY):
   **BUY**: High credibility + bullish catalyst + volume breakout
   **SHORT**: High credibility + bearish/denial + dump setup  
   **NO TRADE**: Everything else (medium/low cred, unverified, passive)

Output ONLY valid JSON:

{
  "ticker": "{ticker}",
  "rumor_summary": "1-sentence recap",
  "credibility": "Low|Medium|High",
  "credibility_reason": "2-3 sentences",
  "references": ["list of URLs or sources used"],
  "trade_signal": "BUY|SHORT|NO_TRADE",
  "confidence": 1-10,
  "trade_rationale": "Why this signal (or no signal)",
  "position_size_pct": 0.5|1|2,
  "stop_loss_pct": 8|10|12,
  "target_pct": 20|30|50
}
"""
# "Verify this information: SMX (SMX (Security Matters) Public Limited Company): The surge was earnings beat + insider buying announced Feb 5."
# news_rumor_prompt = """
# MSTR earning numbers---I seriously gagged when the they came out
# Q4 Financial Summary

# Operating Loss: Operating loss for the fourth quarter of 2025 was $17.4 billion, compared to an operating loss of $1.0 billion for the fourth quarter of 2024. Operating loss for the fourth quarter of 2025 includes an unrealized loss on the Company’s digital assets of $17.4 billion

# Estimated earnings: -.08
# Reported earnings: -42.93
# A negative 53,562 %......WTF? lol
# """

news_rumor_prompt ="""
Hims & Hers (HIMS.N), said in a statement on Saturday that it will stop offering access to the compounded semaglutide pill after the U.S. Food and Drug Administration said it would take action against the telehealth provider for its $49 weight-loss pill.

"Since launching the compounded semaglutide pill on our platform, we’ve had constructive conversations with stakeholders across the industry. As a result, we have decided to stop offering access to this treatment," the company said.

The FDA said on Friday that it plans to restrict GLP-1 ingredients used in non-approved compounded drugs that companies such as Hims and other compounding pharmacies have marketed as alternatives to authorized treatments, citing concerns over quality, safety and potential violations of federal law.

The FDA said it would refer the company to the Department of Justice but did not make clear whether it could quickly halt the sale of the Hims' product, the cheapest GLP-1 therapy on the U.S. market.

Reuters reported on Thursday that Hims would begin offering copies of Novo Nordisk's (NOVOb.CO), new Wegovy pill at an introductory price of $49 per month, about $100 less than the brand name.
"""

async def test():
    llm = LLMService()
    response = await llm.generate(
        prompt=news_rumor_prompt,
        system_prompt=system_prompt,)
    print(response)  # Returns with sources!
    print()
    time.sleep(30)

if __name__ == "__main__":
    asyncio.run(test())
