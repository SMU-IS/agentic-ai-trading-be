"""
LLM-Based Sentiment Analysis Service
File: news-analysis/app/services/_05b_sentiment_llm.py

Per-ticker sentiment analysis using Groq LLM with weighted factor breakdown:
  Final = (market_impact × 0.30) + (tone × 0.40) + (source_quality × 0.10) + (context × 0.20)

Guardrails: retry logic, ticker batching, partial JSON recovery, factor validation.
"""

import asyncio
import json
import logging
import re
from typing import Dict, Optional
from dataclasses import dataclass

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import env_config
from ._05_sentiment_prompts import build_sentiment_prompt

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

FACTOR_WEIGHTS = {
    'market_impact': 0.30,
    'tone': 0.40,
    'source_quality': 0.10,
    'context': 0.20,
}
MAX_RETRIES = 2
MAX_TICKERS_PER_CALL = 5
MAX_TEXT_CHARS = 6000
FALLBACK_REASONING = 'Analysis failed - using neutral fallback'
FALLBACK_FACTORS = {k: 0.0 for k in FACTOR_WEIGHTS}


# ── Data Classes ───────────────────────────────────────────────────────────────

@dataclass
class LLMSentimentResult:
    """Sentiment analysis result for a news item."""
    ticker_sentiments: Dict[str, Dict]
    analysis_successful: bool = True
    error_message: Optional[str] = None


# ── Service ────────────────────────────────────────────────────────────────────

class LLMSentimentService:
    """Per-ticker sentiment analysis using Groq LLM with few-shot prompting."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        model_name: str = env_config.groq_model_name,
        temperature: float = 0.1
    ):
        if self._initialized:
            return

        logger.info("Initializing LLM Sentiment Service...")
        self.model_name = model_name
        try:
            self.llm = ChatGroq(
                model=model_name,
                api_key=env_config.groq_api_key,
                temperature=temperature,
            )
            self.parser = JsonOutputParser()
            logger.info(f"Groq LLM initialized: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Groq LLM: {e}")
            self.llm = None
            self.parser = None

        self._initialized = True

    # ── Public API ─────────────────────────────────────────────────────────────

    async def analyse(self, item: Dict) -> Dict:
        """Analyze sentiment for each ticker in the news item."""
        content = item.get('content', {})
        text = content.get('clean_combined_withurl', '')
        ticker_metadata = item.get('ticker_metadata', {})

        if not ticker_metadata:
            logger.warning("No ticker_metadata found in item")
            item['sentiment_analysis'] = {'error': 'No tickers identified', 'ticker_sentiments': {}}
            return item

        if not text or not text.strip():
            logger.warning("Empty text content")
            item['sentiment_analysis'] = {
                'error': 'Empty content',
                'ticker_sentiments': self._create_fallback_sentiments(ticker_metadata)
            }
            return item

        result = await self._analyze_tickers(text, ticker_metadata)

        # Enrich ticker_metadata with sentiment data
        for ticker, data in result.ticker_sentiments.items():
            if ticker in ticker_metadata:
                ticker_metadata[ticker].update({
                    'sentiment_score': data['sentiment_score'],
                    'sentiment_label': data['sentiment_label'],
                    'sentiment_reasoning': data['reasoning'],
                    'factor_breakdown': data['factor_breakdown'],
                })

        item['ticker_metadata'] = ticker_metadata
        item['sentiment_analysis'] = {
            'analysis_successful': result.analysis_successful,
            'ticker_sentiments': result.ticker_sentiments,
        }
        if result.error_message:
            item['sentiment_analysis']['error'] = result.error_message

        return item

    # ── Analysis Pipeline ──────────────────────────────────────────────────────

    async def _analyze_tickers(self, text: str, ticker_metadata: Dict) -> LLMSentimentResult:
        """Route to batched or single analysis with guardrails."""
        if not self.llm:
            logger.error("LLM not initialized")
            return LLMSentimentResult(
                self._create_fallback_sentiments(ticker_metadata), False, "LLM not initialized"
            )

        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + "..."

        if len(ticker_metadata) > MAX_TICKERS_PER_CALL:
            return await self._analyze_batched(text, ticker_metadata)
        return await self._analyze_single(text, ticker_metadata)

    async def _analyze_batched(self, text: str, ticker_metadata: Dict) -> LLMSentimentResult:
        """Split many-ticker requests into batches to prevent LLM from dropping tickers."""
        ticker_keys = list(ticker_metadata.keys())
        all_sentiments, errors = {}, []
        all_successful = True

        for i in range(0, len(ticker_keys), MAX_TICKERS_PER_CALL):
            batch_keys = ticker_keys[i:i + MAX_TICKERS_PER_CALL]
            batch_meta = {k: ticker_metadata[k] for k in batch_keys}
            logger.info(f"Analyzing ticker batch {i // MAX_TICKERS_PER_CALL + 1}: {batch_keys}")

            result = await self._analyze_single(text, batch_meta)
            all_sentiments.update(result.ticker_sentiments)
            if not result.analysis_successful:
                all_successful = False
                if result.error_message:
                    errors.append(result.error_message)

        return LLMSentimentResult(all_sentiments, all_successful, "; ".join(errors) or None)

    async def _analyze_single(self, text: str, ticker_metadata: Dict) -> LLMSentimentResult:
        """Analyze one batch of tickers with retry logic and partial JSON recovery."""
        tickers_info = self._format_tickers_for_prompt(ticker_metadata)
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                messages = [
                    SystemMessage(content=msg[1]) if msg[0] == "system" else HumanMessage(content=msg[1])
                    for msg in build_sentiment_prompt(text, tickers_info)
                ]
                result = await (self.llm | self.parser).ainvoke(messages)
                return LLMSentimentResult(
                    self._parse_response(result, ticker_metadata), True
                )
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed: {e}")
                # On final attempt, try partial recovery
                if attempt == MAX_RETRIES:
                    recovered = await self._try_recover_partial(text, tickers_info, ticker_metadata)
                    if recovered:
                        return recovered

        logger.error(f"All {MAX_RETRIES} attempts failed: {last_error}")
        return LLMSentimentResult(
            self._create_fallback_sentiments(ticker_metadata), False,
            f"Analysis error after {MAX_RETRIES} attempts: {str(last_error)[:100]}"
        )

    # ── Partial JSON Recovery ──────────────────────────────────────────────────

    async def _try_recover_partial(
        self, text: str, tickers_info: str, ticker_metadata: Dict
    ) -> Optional[LLMSentimentResult]:
        """Bypass JsonOutputParser and extract whatever JSON we can from raw response."""
        try:
            messages = [
                SystemMessage(content=msg[1]) if msg[0] == "system" else HumanMessage(content=msg[1])
                for msg in build_sentiment_prompt(text, tickers_info)
            ]
            raw_response = await self.llm.ainvoke(messages)
            raw_text = raw_response.content if hasattr(raw_response, 'content') else str(raw_response)

            parsed = self._extract_json(raw_text)
            if parsed is None:
                return None

            sentiments = self._parse_response(parsed, ticker_metadata)
            parsed_count = sum(
                1 for s in sentiments.values() if s['reasoning'] != FALLBACK_REASONING
            )
            total = len(ticker_metadata)
            logger.info(f"Partial recovery: {parsed_count}/{total} tickers parsed")

            return LLMSentimentResult(
                sentiments, parsed_count > 0,
                f"Partial recovery: {parsed_count}/{total} tickers" if parsed_count < total else None
            )
        except Exception as e:
            logger.error(f"Partial recovery failed: {e}")
            return None

    def _extract_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from raw LLM output (handles markdown fences, preamble, truncation)."""
        if not text or not text.strip():
            return None

        cleaned = re.sub(r'```(?:json)?\s*', '', text).strip()
        start, end = cleaned.find('{'), cleaned.rfind('}')
        if start == -1 or end <= start:
            return None

        json_str = cleaned[start:end + 1]

        # Try parsing as-is
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # Try repairing truncated JSON (token limit cut mid-object)
        repaired = self._repair_truncated_json(json_str)
        if repaired:
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
        return None

    def _repair_truncated_json(self, json_str: str) -> Optional[str]:
        """Close unmatched braces/brackets from truncated JSON."""
        open_braces = json_str.count('{') - json_str.count('}')
        open_brackets = json_str.count('[') - json_str.count(']')

        if open_braces < 0 or open_brackets < 0:
            return None  # Structurally broken

        if open_braces == 0 and open_brackets == 0:
            return json_str

        repaired = json_str.rstrip()
        repaired = re.sub(r',\s*$', '', repaired)
        repaired = re.sub(r':\s*$', ': null', repaired)
        if repaired.count('"') % 2 == 1:  # odd → unterminated string
            repaired = re.sub(r'"[^"]*$', '""', repaired)
        repaired += ']' * open_brackets + '}' * open_braces
        return repaired

    # ── Response Parsing & Validation ──────────────────────────────────────────

    def _parse_response(self, response: Dict, ticker_metadata: Dict) -> Dict[str, Dict]:
        """Parse LLM response, validate factors, recompute scores server-side."""
        sentiments = {}
        raw = response.get('ticker_sentiments', {})

        for ticker, meta in ticker_metadata.items():
            official_name = meta.get('OfficialName', ticker)

            if ticker not in raw:
                sentiments[ticker] = self._create_fallback_ticker(ticker, official_name)
                continue

            ticker_raw = raw[ticker]
            factors = self._parse_factors(ticker_raw.get('factor_breakdown', {}))

            # Use server-computed score from factors if valid, else fall back to LLM score
            if any(v != 0.0 for v in factors.values()):
                score = self._compute_score(factors)
            else:
                score = max(-1.0, min(1.0, float(ticker_raw.get('sentiment_score', 0.0))))
                logger.warning(f"Invalid factor breakdown for {ticker}, using LLM score: {score}")

            sentiments[ticker] = {
                'sentiment_score': round(score, 4),
                'sentiment_label': 'positive' if score > 0.2 else 'negative' if score < -0.2 else 'neutral',
                'reasoning': ticker_raw.get('reasoning', 'No reasoning provided'),
                'factor_breakdown': factors,
                'official_name': official_name,
            }
        return sentiments

    def _parse_factors(self, raw_factors: Dict) -> Dict[str, float]:
        """Validate and clamp each factor score to [-1.0, 1.0]."""
        factors = {}
        for name in FACTOR_WEIGHTS:
            try:
                factors[name] = max(-1.0, min(1.0, round(float(raw_factors.get(name, 0.0)), 4)))
            except (TypeError, ValueError):
                factors[name] = 0.0
        return factors

    def _compute_score(self, factors: Dict[str, float]) -> float:
        """Compute weighted composite score from factor breakdown."""
        score = sum(factors.get(f, 0.0) * w for f, w in FACTOR_WEIGHTS.items())
        return max(-1.0, min(1.0, round(score, 4)))

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _format_tickers_for_prompt(self, ticker_metadata: Dict) -> str:
        return "\n".join(
            f"- {t} ({info.get('OfficialName', t)}) - Event: {info.get('event_type', 'Unknown')}"
            for t, info in ticker_metadata.items()
        )

    def _create_fallback_sentiments(self, ticker_metadata: Dict) -> Dict[str, Dict]:
        return {
            t: self._create_fallback_ticker(t, info.get('OfficialName', t))
            for t, info in ticker_metadata.items()
        }

    def _create_fallback_ticker(self, ticker: str, official_name: str) -> Dict:
        return {
            'sentiment_score': 0.0,
            'sentiment_label': 'neutral',
            'reasoning': FALLBACK_REASONING,
            'factor_breakdown': dict(FALLBACK_FACTORS),
            'official_name': official_name,
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

llm_sentiment_service = LLMSentimentService()


# ── Testing ────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 80)
    print("LLM SENTIMENT SERVICE TEST")
    print("=" * 80)

    test_item = {
        'content': {
            'clean_combined_withurl': """
            You can own Microsoft at 23x earnings and short Costco at 50x earnings. 
            long AGI, short rotisserie chicken is actually value investing. 
            Buying Microsoft is at this point a no-brainer. GOOG was this cheap while MSFT was in the high 30s. 
            I remind you everyone shat on Google because they were \"behind\" and had looming lawsuits, 
            while justifying Microsofts multiple with their solid position in the business world and their Azure market share. 
            The Google trade seemed too easy to be profitable. 
            And now, everybody thinks each company is vibe-coding their own Office suite, cybersecurity and operating systems lol. 
            Wall street has no idea how software even works. 
            Edit: guys it's a joke, shorting doesn't work out most times, just to show the perspective
            """
        },
        'ticker_metadata': {
            'GOOGL': {'OfficialName': 'Alphabet Inc.', 'event_type': 'INVESTOR_OPINION'},
            'MSFT': {'OfficialName': 'Microsoft Corporation', 'event_type': 'INVESTOR_OPINION'},
            'COST': {'OfficialName': 'Costco Wholesale Corporation', 'event_type': 'INVESTOR_OPINION'},
        }
    }

    result = await LLMSentimentService().analyse(test_item)
    sa = result.get('sentiment_analysis', {})
    print(f"\nSuccess: {sa.get('analysis_successful')}")

    for ticker, data in sa.get('ticker_sentiments', {}).items():
        fb = data.get('factor_breakdown', {})
        print(f"\n  {ticker} ({data['official_name']}): {data['sentiment_score']} [{data['sentiment_label']}]")
        print(f"    MI={fb.get('market_impact')}  T={fb.get('tone')}  SQ={fb.get('source_quality')}  CN={fb.get('context')}")
        print(f"    {data['reasoning']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())