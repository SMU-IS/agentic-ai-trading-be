from typing import Dict
import json

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama

from app.core.config import env_config


class EventIdentifierService:
    """
    Event Identification Service that extracts events from post by llm and a defined list of events.
    If event is not identified, it will fallback to llm to suggest a new event that is not in the list, 
    and update the list of defined events accordingly 
    """
    def __init__(
        self,
        event_list: dict,
        model_type: str = env_config.llm_provider,
        model_name: str = env_config.large_language_model,
        base_url: str = env_config.ollama_base_url,
    ):
        self.model_type = model_type
        self.model_name = model_name
        self.base_url = base_url
        self.event_list = event_list
        self.neweventcount: int = 0

    def _get_llm(self):
        if self.model_type == env_config.llm_provider:
            return ChatOllama(
                model=self.model_name,
                base_url=self.base_url,
                temperature=0,
                format="json",
            )
        raise ValueError(f"Unsupported model type: {self.model_type}")

    # if no event identified from defined list, llm will propose suitable event with confidence score
    def _propose_new_event_with_llm(self, text: str, ticker: str) -> dict:
        llm = self._get_llm()
        parser = JsonOutputParser()

        format_instructions = (
            "Output a JSON object with the following fields:\n"
            "- description (string): A plain-language description of the company event.\n"
            "- proposed_event_name (string): A concise UPPER_SNAKE_CASE name for the event, or null if it matches an existing type.\n"
            "- difference_reason (string): A brief explanation of why this event is materially different from existing ones.\n"
            "- confidence (float): A confidence score between 0 and 1, representing your certainty about the event's significance and accuracy (0 = no confidence, 1 = absolute certainty).\n\n"
            
            "Strict formatting rules:\n"
            "- Use double quotes for all keys and string values.\n"
            "- No trailing commas or extra fields.\n"
            "- Do not include any text, commentary, or metadata outside the JSON object.\n\n"
            
            "Event rules:\n"
            "- Only propose events directly related to the ticker/company.\n"
            "- Focus on events likely to have a material impact on the company's stock price, e.g., product launches, mergers, acquisitions, regulatory changes, earnings surprises.\n"
            "- Ignore general discussion posts, daily threads, memes, or non-specific chatter; set proposed_event_name to null.\n"
            "- Speculative sentiment is allowed only if it reflects market perception of the company's events or situations.\n"
            "- Do not include ticker or company name in proposed_event_name (e.g., use EARNINGS_CALL, not APPLE_EARNINGS_CALL).\n"
            "- Avoid suggesting new event types based on trader behavior or social media chatter.\n"
            "- Do not use UNSPECIFIED_EVENT; if no relevant event is present, set proposed_event_name to null.\n\n"

            f"Known investment event types:\n{', '.join(self.event_list)}\n\n"
            "Ensure the JSON object strictly adheres to this structure and is valid JSON."
        )

        prompt = PromptTemplate(
            template=(
                "You identified an investment-relevant event that does NOT match the existing taxonomy.\n\n"
                "Ticker: {ticker}\n\n"
                "Text:\n{text}\n\n"
                "{format_instructions}"
            ),
            input_variables=["text", "ticker"],
            partial_variables={"format_instructions": format_instructions},
        )

        chain = prompt | llm | parser

        try:
            return chain.invoke({"text": text, "ticker": ticker})
        except json.JSONDecodeError as e:
            print(f"[LLM Event Proposal Error] Malformed JSON: {e}")
            return None
        except Exception as e:
            print(f"[LLM Event Proposal Error] {e}")
            return None


    def _analyse_events_with_llm(self, text: str, ticker_metadata: dict) -> dict:
        llm = self._get_llm()
        parser = JsonOutputParser()

        tickers_json = json.dumps(ticker_metadata, indent=2)

        format_instructions = (
            "Output a JSON object keyed by ticker.\n"
            "Each ticker object must include:\n"
            "- event_type: One of the known investment event types, or null\n"
            "- event_description: Short description of the event from the text, or null\n\n"
            f"Known investment event types:\n{self.event_list['event_types']}\n\n"
            "Classification rules:\n"
            "- Only use the provided event types; do NOT invent new event types.\n"
            "- If the text does not describe a material company event or situation for this ticker, set both fields to null.\n"
            "- Ignore mentions of unrelated assets, indices, commodities, or other companies.\n"
            "- Posts about individual investor actions or positions (e.g., 'I bought', 'I'm holding', 'I sold') should be assigned to INVESTOR_ACTION\n"
            "- Posts expressing opinions, predictions, or subjective sentiment unrelated to company events should be assigned INVESTOR_OPINION.\n"
            "- All posts about investor relevant actions and opinions should be assigned only to either INVESTOR_ACTION or INVESTOR_OPINION\n"
            "- Focus on events that are likely to have a material impact on the company's stock price.\n"
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

        # Initialize default values
        for data in ticker_metadata.values():
            data["event_type"] = None
            data["event_description"] = None
            data["event_proposal"] = None

        try:
            llm_result = chain.invoke({"input_text": text})

            if not isinstance(llm_result, dict):
                return ticker_metadata

            for ticker, result in llm_result.items():
                if ticker not in ticker_metadata or not isinstance(result, dict):
                    continue

                event_type = result.get("event_type")
                event_desc = result.get("event_description")

                normalized_event_type = (
                    event_type.strip().upper()
                    if isinstance(event_type, str)
                    else None
                )

                if normalized_event_type and normalized_event_type not in {
                    "NONE", "NO_EVENT", "NULL", "UNKNOWN", "N/A"
                }:
   
                    ticker_metadata[ticker]["event_type"] = event_type
                    ticker_metadata[ticker]["event_description"] = event_desc
                    continue

                proposal = self._propose_new_event_with_llm(text, ticker)
                if isinstance(proposal, dict):
                    proposed_event_name = proposal.get("proposed_event_name")
                    confidence = proposal.get("confidence")
                    if confidence and confidence >= 0.7 and proposed_event_name:
                        proposed_event_name = proposed_event_name.replace(" ", "_").upper()
                        proposal["proposed_event_name"] = proposed_event_name
                        ticker_metadata[ticker]["event_proposal"] = proposal
                        if proposed_event_name not in self.event_list["event_types"]:
                            self.event_list["event_types"].append(proposed_event_name)
                            self.neweventcount += 1
                            print(f"new event type added: {proposed_event_name}\n\n")

            return ticker_metadata

        except Exception as e:
            print(f"[LLM Event Extraction Error] {e}")
            return ticker_metadata


    
    def analyse_event(self, post: Dict) -> Dict:
        """
        Injects event_type / event_description into ticker_metadata.
        Adds event_proposal if taxonomy misses.
        """
        full_text = post["content"]["clean_combined_withurl"]
        ticker_metadata = post.get("ticker_metadata", {})

        post["ticker_metadata"] = self._analyse_events_with_llm(
            full_text, ticker_metadata
        )

        return post
