from typing import List, Dict, Union
import json
import re
import spacy
import os
from app.core.config import env_config
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama

STOP_SUFFIXES = [
    "inc", "corp", "corporation", "ltd", "llc", "co", "&co", ",inc", ",inc.", "/new", "/de/", "/mn"
]

TICKER_PATTERN = re.compile(r"\$[A-Z]{1,5}(?:\.[A-Z]{1,2})?\b")

class TickerIdentificationService:
    """
    Identification Service that extracts tickers from post by using a hybrid of SpaCy and mapping methods.
    Flow: SpaCy extracts ORG --> Mapping with Company-Ticker list --> Regex for explicit tickers. Falls back
    to LLM identification if SpaCy + Regex returns no result
    Company identified from LLM identification will be used to update alias file to ensure robust mapping
    """

    def __init__(
        self,
        cleaned_tickers_path: str,
        alias_to_canonical_path: str,
        model_type: str = env_config.llm_provider,
        model_name: str = env_config.large_language_model,
        base_url: str = env_config.ollama_base_url,
        spacy_model: str = "en_core_web_lg",
    ):
        self.model_type = model_type
        self.model_name = model_name
        self.base_url = base_url
        self.cleaned_tickers_path = cleaned_tickers_path
        self.alias_to_canonical_path = alias_to_canonical_path

        with open(cleaned_tickers_path, "r", encoding="utf-8") as f:
            self.cleaned_tickers = json.load(f)
        with open(alias_to_canonical_path, "r", encoding="utf-8") as f:
            self.alias_to_canonical = json.load(f)

        self.ticker_to_title = {v["ticker"]: v["title"] for v in self.cleaned_tickers.values()}
        self.ticker_to_canonical = {v["ticker"]: k for k, v in self.cleaned_tickers.items()}
        self.nlp = spacy.load(spacy_model)

    # Normalizes text by converting it to lowercase and removing all characters that are not lowercase letters or digits
    def _normalize_company(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.lower())

    # Remove common company suffixes using regex
    def _remove_suffix(self, name: str) -> str:
        pattern = r"(,?\s*(" + "|".join(STOP_SUFFIXES) + r")\.?)$"
        return re.sub(pattern, "", name, flags=re.IGNORECASE).strip()

    def _get_llm(self):
        return ChatOllama(
            model=self.model_name,
            base_url=self.base_url,
            temperature=0,
            format="json",
        )

    def _extract_company_ticker_llm(self, text: str):
        """
        Use LLM to extract company names and tickers as a fallback.
        Returns a list of dicts: [{"company_name": ..., "ticker": ...}, ...]
        """
        llm = self._get_llm()
        parser = JsonOutputParser()  

        format_instructions = (
            "Output a JSON array of objects, each with two fields: "
            "\"company_name\" (the full name as mentioned in the text) and "
            "\"ticker\" (the stock ticker symbol, or null if not found). "
            "Example: [{\"company_name\": \"Apple Inc.\", \"ticker\": \"AAPL\"}]"
        )

        prompt = PromptTemplate(
            template=(
                "You are a financial text analysis AI. Extract all company names and their associated stock ticker symbols mentioned in the following text.\n"
                "- For each company, return an object with:\n"
                '- "company_name": The full name of the company as mentioned in the text.\n'
                '- "ticker": The stock ticker symbol (if explicitly mentioned or can be confidently inferred), otherwise null.\n'
                "- Only include companies that are clearly referenced as public companies. Consider aliases of the company, for example Google for Alpabet Inc. (GOOGL).\n"
                "- Do not guess tickers. If unsure, set \"ticker\" to null.\n"
                "{format_instructions}\n\n"
                "Text to analyze:\n"
                "{input_text}"
            ),
            input_variables=["input_text"],
            partial_variables={"format_instructions": format_instructions},
        )

        chain = prompt | llm | parser

        try:
            result = chain.invoke({"input_text": text})
            return result
        except Exception as e:
            print(f"LLM extraction error: {e}")
            return []

    def update_alias_mapping(self, new_alias: str, canonical: str):
        # normalize identified alias and update alias mapping
        norm_alias = self._remove_suffix(new_alias)
        norm_alias = self._normalize_company(norm_alias)
        # ensure that alias doesnt exist in mapping and is not ticker
        if norm_alias not in self.alias_to_canonical and norm_alias != canonical:
            self.alias_to_canonical[norm_alias] = canonical
            try:
                # write to alias mapping file
                with open(self.alias_to_canonical_path, "w", encoding="utf-8") as f:
                    json.dump(self.alias_to_canonical, f, ensure_ascii=False, indent=2)
                print(f"Updated alias to canonical mapping with new value: {norm_alias} : {canonical}")
            except IOError as e:
                print(f"Failed to write alias mapping: {e}")


    def extract_tickers(self, text: str) -> Dict[str, Dict[str, List[str]]]:
        """
        Extracts tickers from text using both NER and regex, and falls back to llm if no result found from NER and regex.
        Returns a dictionary (ticker_metadata) mapping tickers to their metadata.
        """
        ticker_metadata: Dict[str, Dict[str, List[str]]] = {}
        doc = self.nlp(text)
        orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]

        # 1. Try direct match and alias match
        for org in orgs:
            # normalized ORG identified
            norm_org = self._remove_suffix(org)
            norm_org = self._normalize_company(norm_org)
            ticker = None
            if norm_org in self.cleaned_tickers:
                ticker = self.cleaned_tickers[norm_org]["ticker"]
            # check for alias with alias to canonical mapping
            elif norm_org in self.alias_to_canonical:
                canonical = self.alias_to_canonical[norm_org]
                if canonical in self.cleaned_tickers:
                    ticker = self.cleaned_tickers[canonical]["ticker"]

            if ticker:
                if ticker not in ticker_metadata:
                    ticker_metadata[ticker] = {
                        "OfficialName": self.ticker_to_title.get(ticker, ""),
                        "NameIdentified": [org]
                    }
                # include all names identified in post for the respective ticker
                else:
                    if org not in ticker_metadata[ticker]["NameIdentified"]:
                        ticker_metadata[ticker]["NameIdentified"].append(org)

        # 2. Regex for explicit tickers
        for match in TICKER_PATTERN.findall(text):
            # normalize ticker
            ticker = match.replace("$", "").upper()
            # check if ticker identified matches our ticker knowledge base
            if ticker in self.ticker_to_title:
                if ticker not in ticker_metadata:
                    ticker_metadata[ticker] = {
                        "OfficialName": self.ticker_to_title.get(ticker, ""),
                        "NameIdentified": [match]
                    }
                else:
                    # include ticker as the name identified in post 
                    if match not in ticker_metadata[ticker]["NameIdentified"]:
                        ticker_metadata[ticker]["NameIdentified"].append(match)

        # 3. Fallback to LLM if nothing found
        if not ticker_metadata:
            llm_result = self._extract_company_ticker_llm(text)
            if llm_result:
                for company in llm_result["companies"]:
                    # check if llm result is empty
                    if company["ticker"] and company["company_name"]:
                        # normalize ticker
                        ticker = company["ticker"].replace("$", "").upper()
                        if ticker in self.ticker_to_title:
                            if ticker not in ticker_metadata:
                                ticker_metadata[ticker] = {
                                    "OfficialName": self.ticker_to_title.get(ticker, ""),
                                    "IdentifiedName": company["company_name"]
                                }
                                # Update alias mapping with name identified by llm
                                self.update_alias_mapping(company["company_name"], self.ticker_to_canonical[ticker])


        return ticker_metadata


    def process_post(self, post: Dict) -> Dict:
        # Add ticker metadata to a single post
        ticker_metadata = self.extract_tickers(post["clean_combined"])
        if ticker_metadata:
            post["ticker_metadata"] = ticker_metadata
            return post
        else:
            print("This post is removed as no ticker was identified:")
            print(post)
            print("\n")
            return None

    def process_input(self, data: Union[List[Dict], Dict]) -> Union[List[Dict], Dict, None]:
        # Process a list or single dict, adding ticker metadata
        if isinstance(data, list):
            return [post for post in (self.process_post(p) for p in data) if post is not None]
        if isinstance(data, dict):
            return self.process_post(data)
        raise TypeError("Input must be a dict or list of dicts")

