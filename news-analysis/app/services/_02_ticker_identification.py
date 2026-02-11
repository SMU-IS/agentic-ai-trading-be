from collections import defaultdict
from typing import List, Dict, Union
import json
import re
import spacy
from app.core.config import env_config
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
import yfinance as yf

STOP_SUFFIXES = [
    "inc", "corp", "corporation", "ltd", "llc", "co", "&co", ",inc", ",inc.", "/new", "/de/", "/mn"
]

TICKER_PATTERN = re.compile(r"\$[A-Z]{1,5}(?:\.[A-Z]{1,2})?\b")


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
        model_type: str = env_config.llm_provider_gemini,
        model_name: str = env_config.large_language_model_gemini or "gemini-2.5-flash-lite",
        google_api_key: str = env_config.gemini_api_key,
        spacy_model: str = "en_core_web_lg",
    ):
        self.model_type = model_type
        self.model_name = model_name
        self.google_api_key = google_api_key
        self.new_alias_count = 0
        self.new_type_count = 0
        self.cleaned_tickers = cleaned_tickers
        self.alias_to_canonical = alias_to_canonical
        self.canonical_to_aliases = self.build_canonical_to_aliases(self.alias_to_canonical)
        self.ticker_to_title = {v["ticker"]: v["title"] for v in self.cleaned_tickers.values()}
        self.ticker_to_canonical = {v["ticker"]: k for k, v in self.cleaned_tickers.items()}
        self.nlp = spacy.load(spacy_model)

    def _normalize_company(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.lower())

    def _remove_suffix(self, name: str) -> str:
        pattern = r"(,?\s*(" + "|".join(STOP_SUFFIXES) + r")\.?)$"
        return re.sub(pattern, "", name, flags=re.IGNORECASE).strip()

    def _get_llm(self):
        return ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=self.google_api_key,
            temperature=0,
        )

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
                print(f"Updated {canon} type to {ticker_type}")
        else:
            ticker_type = cleaned_type
        return ticker_type

    def _extract_company_ticker_llm(self, text: str, orgs: list):
        llm = self._get_llm()
        parser = JsonOutputParser()

        format_instructions = (
            "Output a JSON array of objects. Each object must contain:\n"
            '- "company_name": string\n'
            '- "ticker": string or null\n'
            "Example:\n"
            '[{"company_name": "Apple Inc.", "ticker": "AAPL"."}]'
        )

        org_hint_text = ", ".join(orgs) if orgs else "None detected"

        prompt = PromptTemplate(
            template=(
                "You are a financial entity extraction system used by a bank.\n"
                "Your task is to identify all publicly traded companies mentioned in the text and map each to its correct stock ticker.\n\n"
                "Detected organization mentions from an NER system (may help as hints):\n"
                "{org_hints}\n\n"
                "Instructions:\n"
                "1. Extract ALL publicly traded companies or tickers mentioned.\n"
                "2. Provide for each company:\n"
                "   - company_name: exact name from text\n"
                "   - ticker: official stock ticker symbol\n"
                "3. Use NER hints, but verify and match to official ticker.\n"
                "4. Do NOT guess tickers or include private companies.\n"
                "5. Return each company only once.\n"
                "6. Output strictly as JSON array.\n\n"
                "{format_instructions}\n\n"
                "Text to analyze:\n"
                "{input_text}"
            ),
            input_variables=["input_text", "org_hints"],
            partial_variables={"format_instructions": format_instructions},
        )

        chain = prompt | llm | parser

        try:
            result = chain.invoke({"input_text": text, "org_hints": org_hint_text})

            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    print("LLM returned non-JSON string")
                    return []

            if isinstance(result, dict):
                result = [result]

            if not isinstance(result, list):
                print(f"Unexpected LLM output type: {type(result)}")
                return []

            validated = []
            for item in result:
                # ensure that every item is in dict format 
                if not isinstance(item, dict):
                    continue
                company = item.get("company_name")
                ticker = item.get("ticker")
                # normalize ticker
                if ticker:
                    ticker = ticker.strip().replace("$", "").upper()
                validated.append({
                    "company_name": company,
                    "ticker": ticker,
                })

            return validated
        except Exception as e:
            print(f"LLM extraction error: {e}")
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
            print(f"[Memory Update] Added alias mapping: {norm_alias} -> {canonical}")

    def extract_tickers(self, text: str) -> Dict[str, Dict[str, Union[str, List[str]]]]:
        ticker_metadata: Dict[str, Dict[str, Union[str, List[str]]]] = {}
        doc = self.nlp(text)
        orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]

        # 1. NER + mapping
        for org in orgs:
            print(f"org: {org}")
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
            print(f"match: {match}")
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
        llm_result = self._extract_company_ticker_llm(text, orgs)
        print("check if llm is executed")
        if llm_result:
            print(f"llm results: {llm_result}")
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

    def process_post(self, post: Dict) -> Dict:
        ticker_metadata = self.extract_tickers(post["content"]["clean_combined_withurl"])
        if ticker_metadata:
            post["ticker_metadata"] = ticker_metadata
        else:
            print("This post is removed as no ticker was identified:")
            print(post)
        return post
