from typing import Dict
import json
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama

from app.core.config import env_config
from difflib import SequenceMatcher


class EventIdentifierService:
    """
    Event Identification Service that extracts events from posts by LLM and a defined list of events.
    If event is not identified, LLM will propose a new company/external event (impacting stock) 
    and update the list of defined events accordingly.
    """

    def __init__(
        self,
        event_list: dict,
        model_type: str = env_config.llm_provider,
        model_name: str = env_config.large_language_model,
        base_url: str = env_config.ollama_base_url,
        similarity_threshold: float = 0.6,  # threshold to reject duplicate events
        testflag: bool = False
    ):
        self.model_type = model_type
        self.model_name = model_name
        self.base_url = base_url
        self.event_list = event_list
        # event_name : event_category mapping to be sent to llm
        self.event_list_simple = {k: v["event_category"] for k, v in self.event_list.items()}
        self.neweventcount: int = 0
        self.similarity_threshold = similarity_threshold
        self.testflag = testflag
        self.event_category_map = {}

        self.known_events_str = "\n".join([f"- {k}: {v}" for k, v in self.event_list_simple.items()])
        # map event_data to a list of associated event_names - for similarity checking
        for event_name, data in self.event_list.items():
            category = data.get("event_category", "EXTERNAL_EVENT")
            self.event_category_map.setdefault(category, []).append(event_name)


    def _get_llm(self):
        if self.model_type == env_config.llm_provider:
            return ChatOllama(
                model=self.model_name,
                base_url=self.base_url,
                temperature=0,
                format="json",
            )
        raise ValueError(f"Unsupported model type: {self.model_type}")

    def _propose_new_event_with_llm(self, text: str, ticker: str) -> dict:
        """
        Ask LLM to propose a new company/external event if it affects stock price,
        ignoring investor actions/opinions and events already represented.
        """
        llm = self._get_llm()
        parser = JsonOutputParser()

        format_instructions = (
            "Output a JSON object with the following fields:\n"
            "- description (string): Plain-language description of the company/external event.\n"
            "- proposed_event_name (string): Concise UPPER_SNAKE_CASE name for the event, or null if it exists already or is irrelevant.\n"
            "- event_category (string): One of 'COMPANY_EVENT' or 'EXTERNAL_EVENT'.\n"
            "- meaning (string): Explain the meaning or impact of the event in plain language.\n"
            "- difference_reason (string): Why this event is materially different from existing ones.\n"
            "- confidence (float): 0 to 1 confidence that this event is significant and accurate.\n\n"

            "Rules:\n"
            "- Only propose COMPANY_EVENT or EXTERNAL_EVENT that could materially affect the company's stock price.\n"
            "- Do NOT propose events for investor actions, opinions, minor operational updates, or social chatter; return null in these cases.\n"
            "- proposed_event_name must be generic and descriptive. Do NOT include specific tickers or company names in the event name.\n"
            "- Compare against existing event types. If the event is already represented (even with a different wording or name), return the existing event instead.\n"
            f"Known investment event types (event_name: event_category):\n{self.known_events_str}\n"
            "- Use double quotes, valid JSON, and no extra commentary.\n"
        )

        prompt = PromptTemplate(
            template=(
                "You identified a potentially investment-relevant event that is not in the current taxonomy.\n\n"
                "Ticker: {ticker}\n\n"
                "Text:\n{text}\n\n"
                "{format_instructions}"
            ),
            input_variables=["text", "ticker"],
            partial_variables={"format_instructions": format_instructions},
        )

        chain = prompt | llm | parser

        try:
            result = chain.invoke({"text": text, "ticker": ticker})
            return result
        except Exception as e:
            print(f"[LLM Event Proposal Error] {e}")
            return None

    def is_similar(self, event_name_1: str, event_name_2: str, threshold: float = None) -> bool:
        """Returns True if two strings are more similar than threshold."""
        if threshold is None:
            threshold = self.similarity_threshold
        ratio = SequenceMatcher(None, event_name_1, event_name_2).ratio()
        print(f"Similarity between {event_name_1} and {event_name_2}: {ratio}")
        return ratio >= threshold



    def _analyse_events_with_llm(self, text: str, ticker_metadata: dict) -> dict:
        """
        Classify known events and propose new company/external events if needed.
        """
        llm = self._get_llm()
        parser = JsonOutputParser()

        tickers_json = json.dumps(ticker_metadata, indent=2)
        format_instructions = (
            "You are analyzing a financial/social media post. "
            "Return a valid JSON object with EXACTLY three fields:\n\n"

            "1. `global_category`: One of 'COMPANY_EVENT', 'EXTERNAL_EVENT', or 'INVESTOR_EVENT'. "
            "Determine this FIRST based on the dominant theme of the post.\n\n"

            "2. `primary_tickers`: List of tickers directly affected by the described action or event.\n"
            "Rules for primary_tickers:\n"
            "- Identify the specific sentence/line describing the action or event.\n"
            "- Include ONLY tickers directly involved in that action.\n"
            "- Ignore tickers mentioned for comparison, background, industry context, or commentary.\n"
            "- If the line describes investor behavior (e.g., buying, selling, long, short, trimming, adding, portfolio rebalancing), "
            "ALL tickers mentioned in that action line MUST be included as primary_tickers.\n"
            "- Do NOT omit tickers simply because they appear later in a list.\n\n"

            "3. `tickers`: JSON object keyed ONLY by primary_tickers. Each ticker must contain:\n"
            "- event_category: 'COMPANY_EVENT', 'EXTERNAL_EVENT', or 'INVESTOR_EVENT'.\n"
            "- event_type: Known event type consistent with event_category. "
            "For INVESTOR_EVENT use:\n"
            "    * 'INVESTOR_ACTION' for observable behavior (buying, selling, holding, trimming, adding).\n"
            "    * 'INVESTOR_OPINION' for analysis, sentiment, forecasts, or valuation views.\n"
            "- event_description: Short factual summary of the action/event from the text.\n\n"

            "Additional Rules:\n"
            "- Assign events ONLY to primary_tickers.\n"
            "- If multiple primary_tickers are involved in the same action, they MUST share the same event_type and event_description.\n"
            "- event_type MUST match event_category.\n"
            "- event_type MUST be one of the Known investment event types provided below.\n"
            "- Do NOT invent new event types.\n"
            "- If no matching event_type exists in the Known investment event types, set event_type to null.\n"
            "- If no material event is present, return an empty primary_tickers list and an empty tickers object.\n"
            "- Focus only on material events likely to impact stock price.\n\n"
            f"Known investment event types (event_name: event_category):\n{self.known_events_str}\n"
            "Only classify events as one of these known types.\n"
            "Do not invent new event types unless proposing a new company/external event.\n"
            "Examples:\n"

            "1) Investor Action:\n"
            "Post: 'Investors are buying TSLA and AAPL shares.'\n"
            "{\n"
            "  'global_category': 'INVESTOR_EVENT',\n"
            "  'primary_tickers': ['TSLA', 'AAPL'],\n"
            "  'tickers': {\n"
            "    'TSLA': {'event_category': 'INVESTOR_EVENT', 'event_type': 'INVESTOR_ACTION', 'event_description': 'Investors are buying shares.'},\n"
            "    'AAPL': {'event_category': 'INVESTOR_EVENT', 'event_type': 'INVESTOR_ACTION', 'event_description': 'Investors are buying shares.'}\n"
            "  }\n"
            "}\n\n"

            "2) Investor Opinion:\n"
            "Post: 'Author revises previous valuation model for META.'\n"
            "{\n"
            "  'global_category': 'INVESTOR_EVENT',\n"
            "  'primary_tickers': ['META'],\n"
            "  'tickers': {\n"
            "    'META': {'event_category': 'INVESTOR_EVENT', 'event_type': 'INVESTOR_OPINION', 'event_description': 'Author revises valuation analysis.'}\n"
            "  }\n"
            "}\n\n"

            "3) Company Event (Multiple Tickers):\n"
            "Post: 'Company A and Company B announced a merger. Company C was mentioned for comparison.'\n"
            "{\n"
            "  'global_category': 'COMPANY_EVENT',\n"
            "  'primary_tickers': ['COMPANY_A', 'COMPANY_B'],\n"
            "  'tickers': {\n"
            "    'COMPANY_A': {'event_category': 'COMPANY_EVENT', 'event_type': 'MERGER', 'event_description': 'Two companies announced a merger.'},\n"
            "    'COMPANY_B': {'event_category': 'COMPANY_EVENT', 'event_type': 'MERGER', 'event_description': 'Two companies announced a merger.'}\n"
            "  }\n"
            "}\n"
        )

        prompt = PromptTemplate(
            template=(
                "You are a financial analyst AI.\n"
                "Analyze the following text for investment events.\n\n"
                "Tickers:\n{ticker_metadata_json}\n\n"
                "Text:\n{input_text}\n\n"
                "{format_instructions}"
            ),
            input_variables=["input_text"],
            partial_variables={
                "ticker_metadata_json": tickers_json,
                "format_instructions": format_instructions,
            },
        )

        chain = prompt | llm | parser

        # Initialize defaults
        for data in ticker_metadata.values():
            data["event_type"] = None
            data["event_description"] = None
            data["event_proposal"] = None

        try:
            llm_result = chain.invoke({"input_text": text})
            if not isinstance(llm_result, dict):
                return ticker_metadata

            primary_tickers = llm_result.get("primary_tickers", [])
            tickers_data = llm_result.get("tickers", {})
            if not isinstance(tickers_data, dict):
                return ticker_metadata

            for ticker, result in tickers_data.items():
                if ticker not in ticker_metadata or not isinstance(result, dict):
                    continue
                if ticker not in primary_tickers:
                    continue  # only process primary tickers

                event_type = result.get("event_type")
                event_desc = result.get("event_description")

                if event_type and event_type.upper() not in {"NONE", "NULL", "NO_EVENT"}:
                    ticker_metadata[ticker]["event_type"] = event_type
                    ticker_metadata[ticker]["event_description"] = event_desc
                    continue

                # Propose new event if nothing matched
                proposal = self._propose_new_event_with_llm(text, ticker)
                final_proposal = None

                if isinstance(proposal, dict):
                    prop_name = proposal.get("proposed_event_name")
                    confidence = proposal.get("confidence", 0)

                    if confidence >= 0.75 and prop_name and proposal.get("meaning") and proposal.get("event_category"):
                        prop_name = prop_name.replace(" ", "_").upper()
                        category = proposal["event_category"]

                        # Ensure category exists in map
                        category_events = self.event_category_map.setdefault(category, [])

                        # Check for existing similar event
                        existing_similar_event = next(
                            (e for e in category_events if self.is_similar(prop_name, e)), None
                        )

                        if existing_similar_event:
                            # Use the existing event
                            prop_name = existing_similar_event
                            proposal["proposed_event_name"] = prop_name
                            proposal["similar_event_found"] = True
                            print(f"[INFO] Similar event found for {ticker}, using existing: {prop_name}")
                        else:
                            # Add as new event
                            self.event_list[prop_name] = {
                                "event_category": category,
                                "meaning": proposal["meaning"],
                            }
                            category_events.append(prop_name)
                            self.known_events_str += f"\n- {prop_name}: {category}"
                            self.neweventcount += 1
                            print(f"[INFO] New event added ({self.neweventcount}): {prop_name}")
                            proposal["similar_event_found"] = False


                        final_proposal = proposal

                # Assign proposal to ticker once
                if final_proposal:
                    ticker_metadata[ticker]["event_proposal"] = final_proposal

            return ticker_metadata

        except Exception as e:
            print(f"[LLM Event Extraction Error] {e}")
            return ticker_metadata

    def analyse_event(self, post: Dict) -> Dict:
        """
        Injects event_type / event_description into ticker_metadata.
        Adds event_proposal if taxonomy misses.
        """
        full_text = post["content"].get("clean_combined_withurl", "")
        ticker_metadata = post.get("ticker_metadata", {})

        post["ticker_metadata"] = self._analyse_events_with_llm(
            full_text, ticker_metadata
        )

        return post
