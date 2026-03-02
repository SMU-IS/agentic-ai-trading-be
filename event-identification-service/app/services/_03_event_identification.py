from app.core.config import env_config
from typing import Dict
import json
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from difflib import SequenceMatcher
from app.core.logger import logger



class EventIdentifierService:
    """
    Event Identification Service that extracts events from posts by LLM and a defined list of events.
    If event is not identified, LLM will propose a new company/external event (impacting stock) 
    and update the list of defined events accordingly.
    """

    def __init__(
        self,
        event_list: dict,
        model_name: str = env_config.groq_model_name,
        groq_api_key: str = env_config.groq_api_key,
        similarity_threshold: float = 0.7,  # threshold to reject duplicate events
        testflag: bool = False
    ):
        self.model_name = model_name
        self.groq_api_key = groq_api_key
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
            self.event_category_map.setdefault("EXTERNAL_EVENT", []).append(event_name)
            self.event_category_map.setdefault("COMPANY_EVENT", []).append(event_name)

        try:
            logger.info("Initializing LLM Ticker Identification Service...")

            self.llm = ChatGroq(
                model=self.model_name,
                api_key=self.groq_api_key,
                temperature=0.1,
            )
            self.parser = JsonOutputParser()
            logger.info(f"Groq LLM initialized: {model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Groq LLM: {e}")
            self.llm = None
            self.parser = None


    def is_similar(self, event_name_1: str, event_name_2: str, threshold: float = None) -> bool:
        """Returns True if two strings are more similar than threshold."""
        if threshold is None:
            threshold = self.similarity_threshold
        ratio = SequenceMatcher(None, event_name_1, event_name_2).ratio()
        logger.info(f"Similarity between {event_name_1} and {event_name_2}: {ratio}")
        return ratio >= threshold



    def _propose_new_events_with_llm(
        self,
        text: str,
        unmatched_tickers: dict,
    ) -> dict:
        """
        Propose new taxonomy events for unmatched tickers.

        unmatched_tickers = {
            TICKER: {
                "primary_event_category": "COMPANY_EVENT" or "EXTERNAL_EVENT"
            }
        }

        Returns:
        {
            TICKER: {
                "primary_event_category": str,
                "proposed_event_name": str or null,
                "proposed_description": str or null,
                "meaning": str or null,
                "confidence": float
            }
        }
        """

        if not unmatched_tickers:
            return {}


        unmatched_json = json.dumps(unmatched_tickers, indent=2)

        format_instructions = (
            "For each ticker below:\n"
            "- Only propose a NEW event within its provided primary_event_category.\n"
            "- You MUST return the same primary_event_category in your output.\n"
            "- Do NOT switch categories.\n"
            "- Only propose events that could materially affect stock price.\n"
            "- Do NOT propose events for investor sentiment, opinions, "
            "minor operational updates, or social chatter.\n"
            "- If no meaningful new event exists, return null for that ticker.\n\n"

            "Return JSON structured exactly as:\n"
            "{\n"
            '  "TICKER": {\n'
            '    "primary_event_category": "COMPANY_EVENT or EXTERNAL_EVENT",\n'
            '    "proposed_event_name": "UPPER_SNAKE_CASE" or null,\n'
            '    "proposed_description": Short factual summary,\n'
            '    "meaning": "plain language explanation" or null,\n'
            '    "confidence": float (0 to 1)\n'
            "  }\n"
            "}\n\n"

            "Rules:\n"
            "- proposed_event_name must be generic and reusable.\n"
            "- Do NOT include ticker symbols or company names in the event name.\n"
            "- An event must refer to a specific, identifiable occurrence.\n"
            "- Do NOT classify broad industry trends, long-term cycles, or thematic narratives as events.\n"
            "- primary_event_category must EXACTLY match the input category.\n"
            "- Use valid JSON with double quotes only.\n"
            "- No extra commentary.\n"
        )

        prompt = PromptTemplate(
            template=(
                "You are reviewing financial text that contains events "
                "not currently represented in the taxonomy.\n\n"
                "Full Post:\n{text}\n\n"
                "Unmatched Tickers (with fixed primary categories):\n"
                "{unmatched}\n\n"
                "{format_instructions}\n"
                "Return strictly valid JSON."
            ),
            input_variables=["text"],
            partial_variables={
                "unmatched": unmatched_json,
                "format_instructions": format_instructions,
            },
        )

        chain = prompt | self.llm | self.parser

        try:
            result = chain.invoke({"text": text})

            if not isinstance(result, dict):
                return {}

            # Optional: Hard validation safeguard
            for ticker, data in result.items():
                input_category = unmatched_tickers.get(ticker, {}).get("primary_event_category")
                if data.get("primary_event_category") != input_category:
                    # Force correction if model drifts
                    data["primary_event_category"] = input_category

            return result

        except Exception as e:
            logger.error(f"[LLM Event Proposal Error] {e}")
            return {}

    def _identify_primary_tickers(self, text: str, ticker_metadata: dict) -> dict:
        """
        Identify primary tickers and classify dominant event category per ticker.
        Returns:
            {
                "primary_tickers": [...],
                "tickers": {
                    TICKER: {
                        "primary_event_category": ...,
                        "event_description": ...
                    }
                }
            }
        """

        tickers_json = json.dumps(ticker_metadata, indent=2)

        format_instructions = (
            "You are a financial event classification system.\n\n"

            "Return a valid JSON object with EXACTLY two fields:\n\n"

            "1. \"primary_tickers\": List of materially affected tickers.\n"
            "- Select ONLY tickers from the provided Tickers list.\n"
            "- Include a ticker ONLY if the post's main purpose centers on that company.\n"
            "- Include only companies whose fundamentals or capital allocation are directly affected.\n"
            "- Exclude tickers mentioned casually, hypothetically, metaphorically, or as background history.\n"
            "- If no company is materially discussed, return an empty list.\n\n"

            "2. \"tickers\": JSON object keyed ONLY by primary_tickers.\n"
            "   For EACH ticker return:\n"
            "   - primary_event_category: ONE of:\n"
            "     INVESTOR_ACTION: A trade already executed and central to the post.\n"
            "     INVESTOR_OPINION: Belief, speculation, advice, analysis, or planned trade.\n"
            "     COMPANY_EVENT: A recent or newly announced corporate action or operational change initiated or controlled by the company, including insider transactions by executives or directors (e.g., CEO stock sales or purchases).\n"
            "     EXTERNAL_EVENT: A catalyst initiated by a government, regulator, court, competitor, or macro force.\n"
            "   - event_description: Short factual summary.\n\n"

            "Dominance Rules:\n"
            "- First determine the dominant intent of the post.\n"
            "- Events must describe a discrete, identifiable occurrence.\n"
            "- Do NOT classify historical facts, existing products, long-standing strategy, broad themes, or ongoing industry narratives as events.\n"
            "- Use INVESTOR_ACTION only if an executed trade is the main focus.\n"
            "- If the post asks for advice, classify as INVESTOR_OPINION.\n"
            "- Hypothetical or planned trades = INVESTOR_OPINION.\n"
            "- If multiple signals exist, choose the category matching dominant intent.\n"
            "- If unsure between ACTION and OPINION, choose INVESTOR_OPINION.\n\n"

            "Constraints:\n"
            "- primary_event_category must be EXACTLY one of the four provided values. Any other value is invalid.\n"
            "- Assign events ONLY to primary_tickers.\n"
            "- If no clear category, exclude the ticker.\n\n"

            "Return strictly valid JSON. No explanations."
        )

        prompt = PromptTemplate(
            template=(
                "You are a financial entity extraction system.\n\n"
                "Post:\n{text}\n\n"
                "Tickers:\n{ticker_metadata_json}\n\n"
                "{format_instructions}"
            ),
            input_variables=["text"], 
            partial_variables={
                "ticker_metadata_json": tickers_json,
                "format_instructions": format_instructions,
            },
        )

        chain = prompt | self.llm | self.parser
        try:
            # Initialize defaults
            for data in ticker_metadata.values():
                data["event_type"] = None
                data["event_description"] = None
                data["event_proposal"] = None
            ticker_keys = ticker_metadata.keys()
            result = chain.invoke({"text": text})

            if not isinstance(result, dict):
                return {"primary_tickers": [], "tickers": {}}

            primary = result.get("primary_tickers") or []
            tickers = result.get("tickers") or {}
            valid_tickers_for_taxonomy = {}
            unmatched = {}
            category_present = set()


            for ticker, data in tickers.items():
                event_type = data.get("primary_event_category")
                event_description = data.get("event_description")

                if ticker not in ticker_keys:
                    continue

                if not event_type:
                    continue

                # Handle behavioral events immediately
                if event_type in {"INVESTOR_ACTION", "INVESTOR_OPINION"}:
                    ticker_metadata[ticker]["event_type"] = event_type
                    ticker_metadata[ticker]["event_description"] = event_description
                    continue

                # Company / External → send to taxonomy stage
                category_present.add(event_type)
                valid_tickers_for_taxonomy[ticker] = data

            # Build taxonomy map once

            event_category_map = {
                category: [
                    event_name
                    for event_name, meta in self.event_list.items()
                    if meta.get("event_category") == category
                ]
                for category in category_present
            }
        
            # Pass only company/external tickers to taxonomy stage
            if valid_tickers_for_taxonomy:

                event_results = self._analyse_events_with_llm(
                    valid_tickers_for_taxonomy,
                    event_category_map
                )
            else:
                event_results = {"tickers": {}}

            # ---------------------------------------------------
            # Merge refined taxonomy results back
            # ---------------------------------------------------
            if isinstance(event_results, dict):
                refined = event_results.get("tickers", {})

                for ticker, data in refined.items():
                    if ticker in ticker_metadata:
                        refined_event_type = data.get("event_type")
                        refined_description = data.get("event_description")
                        if refined_event_type and refined_description:
                            ticker_metadata[ticker]["event_type"] = refined_event_type
                            ticker_metadata[ticker]["event_description"] = refined_description
                        if refined_event_type is None:
                            unmatched[ticker] = {"primary_event_category": data.get("primary_event_category")}
                if unmatched:
                    proposals = self._propose_new_events_with_llm(text, unmatched)
                    for ticker, proposal in proposals.items():
                        final_proposal = None

                        if isinstance(proposal, dict):
                            prop_name = proposal.get("proposed_event_name")
                            event_category = proposal.get("primary_event_category")
                            confidence = proposal.get("confidence", 0)

                            if confidence >= 0.75 and prop_name and proposal.get("meaning"):
                                prop_name = prop_name.replace(" ", "_").upper()

                                # Ensure category exists in map
                                category_events = self.event_category_map.setdefault(event_category, [])
                                
                                # Check for existing similar event
                                existing_similar_event = next(
                                    (e for e in category_events if self.is_similar(prop_name, e)), None
                                )

                                if existing_similar_event:
                                    # Use the existing event
                                    prop_name = existing_similar_event
                                    proposal["proposed_event_name"] = prop_name
                                    proposal["similar_event_found"] = True
                                    logger.info(f"[INFO] Similar event found for {ticker}, using existing: {prop_name}")
                                else:
                                    # Add as new event
                                    self.event_list[prop_name] = {
                                        "event_category": event_category,
                                        "meaning": proposal["meaning"],
                                    }
                                    category_events.append(prop_name)
                                    self.neweventcount += 1
                                    logger.info(f"[INFO] New event added ({self.neweventcount}): {prop_name}")
                                    proposal["similar_event_found"] = False


                                final_proposal = proposal

                        # Assign proposal to ticker once
                        if final_proposal:
                            ticker_metadata[ticker]["event_proposal"] = final_proposal


            return ticker_metadata
        
        except Exception as e:
            logger.error(f"[LLM Event Extraction Error] {e}")
            return ticker_metadata


    def _analyse_events_with_llm(
        self,
        ticker_inputs: dict,
        event_category_map: dict,
    ) -> dict:
        """
        Second-stage refinement.

        Input:
            ticker_inputs = {
                TICKER: {
                    "primary_event_category": ...,
                    "event_description": ...
                }
            }

            event_category_map = {
                CATEGORY: [event_type_1, event_type_2, ...]
            }

        Goal:
            For each ticker, pick the most specific event_type
            from its detected category taxonomy.
        """

        if not ticker_inputs:
            return {}


        taxonomy_str = json.dumps(event_category_map, indent=2)
        ticker_str = json.dumps(ticker_inputs, indent=2)

        format_instructions = (
            "You are refining event classification.\n\n"

            "You are given:\n"
            "1) Tickers requiring refinement\n"
            "2) A filtered taxonomy per category\n\n"

            "For each ticker:\n"
            "- Select the most specific event_type from the provided taxonomy\n"
            "- Match it against the event description\n"
            "- Interpret the description in relation to the company's role in the value chain.\n"
            "- The same industry development may be positive or negative depending on whether the company is a producer, consumer, or intermediary.\n"
            "- If no match fits, return null\n\n"

            "Return JSON:\n"
            "{\n"
            "  \"tickers\": {\n"
            "     TICKER: {\n"
            "        \"primary_event_category\": from ticker_inputs\n"
            "        \"event_type\": <string or null>,\n"
            "        \"event_description\": \"refined description\"\n"
            "     }\n"
            "  }\n"
            "}\n\n"

            f"Taxonomy:\n{taxonomy_str}\n\n"
            f"Tickers to classify:\n{ticker_str}\n\n"
            "Return strictly valid JSON."
        )

        prompt = PromptTemplate(
            template=(
                "You are a financial event resolver.\n\n"
                "{format_instructions}"
            ),
            input_variables=[],
            partial_variables={
                "format_instructions": format_instructions,
            },
        )

        chain = prompt | self.llm | self.parser

        try:
            result = chain.invoke({})

            if (
                not isinstance(result, dict)
                or "tickers" not in result
                or not isinstance(result["tickers"], dict)
            ):
                return ticker_inputs

            return result
        
        except Exception as e:
            logger.error(f"[Event Refinement Error] {e}")
            return ticker_inputs


    def analyse_event(self, post: Dict) -> Dict:
        """
        Injects event_type / event_description into ticker_metadata.
        Adds event_proposal if taxonomy misses.
        """
        full_text = post["content"].get("clean_combined_withurl", "")
        ticker_metadata = post.get("ticker_metadata", {})

        post["ticker_metadata"] = self._identify_primary_tickers(
            full_text, ticker_metadata
        )

        return post
