import asyncio
from app.core.logger import logger
from collections import defaultdict
from typing import List, Dict, Union
import json
import re
import spacy
from app.core.config import env_config
from langchain_groq import ChatGroq
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
import yfinance as yf

STOP_SUFFIXES = [
    "inc", "corp", "corporation", "ltd", "llc", "co", "&co", ",inc", ",inc.", "/new", "/de/", "/mn"
]

TICKER_PATTERN = re.compile(r"\$[A-Z]{1,5}(?:\.[A-Z]{1,2})?\b")

LLM_MAX_RETRIES = 3
LLM_RETRY_DELAY = 2.0   


class TickerIdentificationService:
    """
    Identification Service that extracts tickers from text using a hybrid approach:
    1. NER with SpaCy
    2. Mapping with cleaned tickers and alias mapping
    3. Regex for explicit tickers
    4. LLM to identify additional tickers in text 
    """

    def __init__(
        self,
        cleaned_tickers: dict,
        alias_to_canonical: dict,
        groq_api_key: str = env_config.groq_api_key,
        spacy_model: str = "en_core_web_lg",
        model_name: str = env_config.groq_model_name,

    ):
        self.model_name = model_name
        self.groq_api_key = groq_api_key
        self.new_alias_count = 0
        self.new_type_count = 0
        self.cleaned_tickers = cleaned_tickers
        self.alias_to_canonical = alias_to_canonical
        self.canonical_to_aliases = self.build_canonical_to_aliases(self.alias_to_canonical)
        self.ticker_to_title = {v["ticker"]: v["title"] for v in self.cleaned_tickers.values()}
        self.ticker_to_canonical = {v["ticker"]: k for k, v in self.cleaned_tickers.items()}
        self.nlp = spacy.load(spacy_model)
        
        try:
            logger.info("Initializing LLM Ticker Identification Service...")

            self.llm = ChatGroq(
                model=self.model_name,
                api_key=self.groq_api_key,
                temperature=0,
            )
            self.parser = JsonOutputParser()
            logger.info(f"Groq LLM initialized: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Groq LLM: {e}")
            self.llm = None
            self.parser = None

    def _normalize_company(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.lower())

    def _remove_suffix(self, name: str) -> str:
        pattern = r"(,?\s*(" + "|".join(STOP_SUFFIXES) + r")\.?)$"
        return re.sub(pattern, "", name, flags=re.IGNORECASE).strip()
           

    # use yahoo finance to classify ticker 
    def classify_ticker(self, ticker: str) -> str:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            quote_type = info.get("quoteType")
            mapping = {
                "EQUITY": "stock",
                "ETF": "etf",
                "CRYPTOCURRENCY": "crypto",
                "INDEX": "index",
                "CURRENCY": "forex"
            }
            return mapping.get(quote_type)
        except Exception:
            return None

    # check if ticker type already exists in cleaned ticker mapping, otherwise call classify_ticker method
    def _update_cleaned_entry(self, ticker: str) -> Union[str, None]:
        canon = self.ticker_to_canonical.get(ticker)
        if not canon:
            return None
        cleaned_entry = self.cleaned_tickers.get(canon, {})
        cleaned_type = cleaned_entry.get("type")
        if cleaned_type is None:
            ticker_type = self.classify_ticker(ticker)
            if ticker_type:
                self.new_type_count += 1
                cleaned_entry["type"] = ticker_type
                self.cleaned_tickers[canon] = cleaned_entry
                logger.info(f"Updated {canon} type to {ticker_type}")
        else:
            ticker_type = cleaned_type
        return ticker_type

    async def _extract_company_ticker_llm(self, text: str) -> list:
        if not self.llm:
            return []
        format_instructions = (
            "Output a JSON array of objects. Each object must contain:\n"
            '- "company_name": string\n'
            '- "ticker": string or null\n'
            "Example:\n"
            '[{"company_name": "Apple Inc.", "ticker": "AAPL"}]\n'
            'Return strictly valid json array output. DO NOT include comments.'
        )

        prompt = PromptTemplate(
            template=(
                "You are a financial entity extraction system used by a bank.\n"
                "Your task is to identify all publicly traded companies mentioned in the text and map each to its correct stock ticker.\n\n"
                "Instructions:\n"
                "1. Extract ALL publicly traded companies or tickers mentioned.\n"
                "2. Provide for each company:\n"
                "   - company_name: exact name from text\n"
                "   - ticker: official stock ticker symbol\n"
                "3. Use NER hints, but verify and match to official ticker.\n"
                "4. Do NOT guess tickers or include private companies.\n"
                "5. Return each company only once.\n"
                "6. If multiple ticker symbols represent the same company (e.g., share classes), return the normalized SEC ticker. (e.g., Return GOOGL for GOOG which is an Alphabet class share)."
                "6. Output strictly as JSON array.\n\n"
                "{format_instructions}\n\n"
                "Text to analyze:\n"
                "{input_text}"
            ),
            input_variables=["input_text"],
            partial_variables={"format_instructions": format_instructions},
        )

        chain = prompt | self.llm | self.parser
        for attempt in range(1, LLM_MAX_RETRIES + 1):
                
            try:
                result = await chain.ainvoke({"input_text": text})

                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except json.JSONDecodeError:
                        raise ValueError(f"LLM returned non-JSON string: {result[:200]}")

                if isinstance(result, dict):
                    result = [result]

                if not isinstance(result, list):
                    raise ValueError(f"Unexpected LLM output type: {type(result)}")

                validated = []
                for item in result:
                    # ensure that every item is in dict format 
                    if not isinstance(item, dict):
                        continue
                    company = item.get("company_name")
                    ticker = item.get("ticker")
                    if not company:
                        continue
                    # normalize ticker
                    if ticker:
                        ticker = ticker.strip().replace("$", "").upper()
                    validated.append({
                        "company_name": company,
                        "ticker": ticker,
                    })

                logger.debug(f"[Ticker LLM] Success on attempt {attempt} — {len(validated)} tickers")
                return validated

            except Exception as e:
                logger.warning(f"[Ticker LLM] Attempt {attempt}/{LLM_MAX_RETRIES} failed: {e}")
                if attempt < LLM_MAX_RETRIES:
                    await asyncio.sleep(LLM_RETRY_DELAY * attempt)
                else:
                    logger.error(f"[Ticker LLM] All {LLM_MAX_RETRIES} attempts failed — returning empty")
                    return []

    def build_canonical_to_aliases(self, alias_to_canonical: Dict[str, str]) -> Dict[str, List[str]]:
        canonical_to_aliases = defaultdict(list)
        for alias, canonical in alias_to_canonical.items():
            canonical_to_aliases[canonical].append(alias)
        return canonical_to_aliases

    def update_alias_mapping(self, new_alias: str, canonical: str) -> bool:
        norm_alias = self._normalize_company(self._remove_suffix(new_alias))
        if norm_alias not in self.alias_to_canonical and norm_alias != canonical:
            self.alias_to_canonical[norm_alias] = canonical
            self.new_alias_count += 1
            logger.info(f"[Memory Update] Added alias mapping: {norm_alias} -> {canonical}")

    def get_aliases(self, tickers: List[str]) -> Dict[str, Dict[str, List[str]]]:
        output = {}
        for ticker in tickers:
            canonical = self.ticker_to_canonical.get(ticker)
            output[ticker] = {
                "OfficialName": self.ticker_to_title.get(ticker, ""),
                "Aliases": self.canonical_to_aliases.get(canonical, []) if canonical else []
            }

        return output

    async def extract_tickers(self, text: str) -> Dict[str, Dict[str, Union[str, List[str]]]]:
        ticker_metadata: Dict[str, Dict[str, Union[str, List[str]]]] = {}
        doc = self.nlp(text)
        orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]

        # 1. NER + mapping
        for org in orgs:
            norm_org = self._normalize_company(self._remove_suffix(org))
            ticker = None
            name_identified = ""
            if norm_org in self.cleaned_tickers:
                ticker = self.cleaned_tickers[norm_org]["ticker"]
                name_identified = norm_org
            elif norm_org in self.alias_to_canonical:
                canonical = self.alias_to_canonical[norm_org]
                if canonical in self.cleaned_tickers:
                    ticker = self.cleaned_tickers[canonical]["ticker"]
                    name_identified = norm_org

            if name_identified and ticker and ticker in self.ticker_to_title:
                if ticker not in ticker_metadata:
                    ticker_type = self._update_cleaned_entry(ticker)
                    if ticker_type != "stock":
                        continue
                    ticker_metadata[ticker] = {
                        "type": ticker_type,
                        "official_name": self.ticker_to_title.get(ticker, ""),
                        "name_identified": [name_identified]
                    }
                else:
                    if name_identified not in ticker_metadata[ticker]["name_identified"]:
                        ticker_metadata[ticker]["name_identified"].append(name_identified)

        # 2. Regex tickers
        for match in TICKER_PATTERN.findall(text):
            ticker = match.replace("$", "").upper()
            if ticker in self.ticker_to_title:
                if ticker not in ticker_metadata:
                    ticker_type = self._update_cleaned_entry(ticker)
                    if ticker_type != "stock":
                        continue
                    ticker_metadata[ticker] = {
                        "type": ticker_type,
                        "official_name": self.ticker_to_title.get(ticker, ""),
                        "name_identified": [match]
                    }
                else:
                    if match not in ticker_metadata[ticker]["name_identified"]:
                        ticker_metadata[ticker]["name_identified"].append(match)

        # 3. LLM
        llm_result = await self._extract_company_ticker_llm(text)
        if llm_result:
            for company in llm_result:
                if company:
                    company_name = company.get("company_name")
                    ticker = company.get("ticker")
                    if company_name and ticker in self.ticker_to_title:
                        if ticker not in ticker_metadata:
                            ticker_type = self._update_cleaned_entry(ticker)
                            if ticker_type != "stock":
                                continue
                            ticker_metadata[ticker] = {
                                "type": ticker_type,
                                "official_name": self.ticker_to_title.get(ticker, ""),
                                "name_identified": [company_name]
                            }
                            self.update_alias_mapping(company_name, self.ticker_to_canonical[ticker])
                        else:
                            if company_name not in ticker_metadata[ticker]["name_identified"]:
                                ticker_metadata[ticker]["name_identified"].append(company_name)
        return ticker_metadata

    async def process_post(self, post: Dict) -> Dict:
        post_metadata = post.get("metadata", {})
        raw_tickers = post_metadata.get("ticker", []) if post_metadata else []

        # normalise to list — handle both string and list formats
        if isinstance(raw_tickers, str):
            provided_tickers = [raw_tickers] if raw_tickers.strip() else []
        elif isinstance(raw_tickers, list):
            provided_tickers = raw_tickers
        else:
            provided_tickers = []

        if provided_tickers:
            # use provided tickers directly — skip NER + regex + LLM
            ticker_metadata = {}
            for ticker in provided_tickers:
                ticker = ticker.strip().upper()
                if ticker not in self.ticker_to_title:
                    logger.info(f"Provided ticker {ticker} not in mapping — skipping")
                    continue
                ticker_type = self._update_cleaned_entry(ticker)
                if ticker_type != "stock":
                    continue
                ticker_metadata[ticker] = {
                    "type": ticker_type,
                    "official_name": self.ticker_to_title.get(ticker, ""),
                    "name_identified": [ticker],  # set as itself since no NER name
                }
        else:
            # fallback to full extraction pipeline
            ticker_metadata = await self.extract_tickers(post["content"]["clean_combined_withurl"])

        if ticker_metadata:
            post["ticker_metadata"] = ticker_metadata
        else:
            postid = post.get("id")
            logger.info(f"This post is removed as no ticker was identified: {postid}")

        return post
