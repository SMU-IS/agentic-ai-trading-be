from typing import List
from src.models.news import TickerTopic, DeepAnalysis, ResearchQuestion
from src.services.llm_service import LLMService

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

sample_news_prompt ="""
Hims & Hers (HIMS.N), said in a statement on Saturday that it will stop offering access to the compounded semaglutide pill after the U.S. Food and Drug Administration said it would take action against the telehealth provider for its $49 weight-loss pill.

"Since launching the compounded semaglutide pill on our platform, we’ve had constructive conversations with stakeholders across the industry. As a result, we have decided to stop offering access to this treatment," the company said.

The FDA said on Friday that it plans to restrict GLP-1 ingredients used in non-approved compounded drugs that companies such as Hims and other compounding pharmacies have marketed as alternatives to authorized treatments, citing concerns over quality, safety and potential violations of federal law.

The FDA said it would refer the company to the Department of Justice but did not make clear whether it could quickly halt the sale of the Hims' product, the cheapest GLP-1 therapy on the U.S. market.

Reuters reported on Thursday that Hims would begin offering copies of Novo Nordisk's (NOVOb.CO), new Wegovy pill at an introductory price of $49 per month, about $100 less than the brand name.
"""

class DeepAnalyzer:
    def __init__(self, llm: LLMService):
        self.llm = llm
    
    async def analyze(self, news_content: str) -> DeepAnalysis:
        # Generate research questions
        questions_prompt = f"""
        These are the latest news collected:
        {news_content}
        """
        
        analysis_json = await self.llm.generate_parse_json(prompt=questions_prompt, system_prompt=system_prompt, model_class=DeepAnalysis)
        return analysis_json


async def test():
    llm = LLMService()
    analyzer = DeepAnalyzer(llm)
    analysis = await analyzer.analyze(sample_news_prompt)
    print_analysis(analysis)


def print_analysis(analysis: DeepAnalysis):
    """Print DeepAnalysis in trading terminal format"""
    print("\n" + "="*80)
    print(f"📊 DEEP ANALYSIS REPORT - {analysis.ticker}")
    print("="*80)
    
    # Summary row
    signal_emoji = {"BUY": "🟢", "SHORT": "🔴", "NO_TRADE": "⚪"}
    print(f"{signal_emoji[analysis.trade_signal]} {analysis.trade_signal:<10} Confidence: {analysis.confidence}/10")
    print(f"   📈 Position: {analysis.position_size_pct}% | Stop: {analysis.stop_loss_pct}% | Target: {analysis.target_pct}%")
    
    print(f"\n💬 Rumor: {analysis.rumor_summary}")
    print(f"🔍 Credibility: {analysis.credibility:<7} ({analysis.confidence}/10)")
    print(f"📝 Reason: {analysis.credibility_reason}")
    
    if analysis.references:
        print(f"🔗 Sources ({len(analysis.references)}):")
        for i, ref in enumerate(analysis.references[:3], 1):  # First 3
            print(f"   {i}. {ref}")
        if len(analysis.references) > 3:
            print(f"   ... +{len(analysis.references)-3} more")
    
    print(f"\n⚙️  TRADE RATIONALE: {analysis.trade_rationale}")
    print("="*80 + "\n")


if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test())