from typing import Dict
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama
import json

from app.core.config import env_config


class EventIdentifierService:
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

    def _get_llm(self):
        if self.model_type == env_config.llm_provider:
            return ChatOllama(
                model=self.model_name,
                base_url=self.base_url,
                temperature=0,
                format="json",
            )
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")

    def _analyse_events_with_llm(self, text: str, ticker_metadata: dict) -> dict:
        """
        Use LLM to extract investment events and include them in ticker_metadata based on a list of defined events.
        """
        llm = self._get_llm()
        parser = JsonOutputParser()

        tickers_json = json.dumps(ticker_metadata, indent=2)
        events_json = json.dumps(self.event_list["event_types"], indent=2)

        format_instructions = (
            "Output a JSON object keyed by ticker. Each ticker object should include:\n"
            "- event_type: One of the known investment event types provided, or null if none\n"
            "- event_description: Short description of the event from the text, or null if none\n"
            f"Known investment event types:\n {events_json})\n"
            "Only include event if it is in the known investment event types.\n"
            "Only include fields if an event is clearly supported by the text.\n"
            "If no event is identified, set both fields to null."
        )

        prompt = PromptTemplate(
            template=(
                "You are a financial analyst AI.\n"
                "Analyze the following text for investment events and associate them with the tickers provided.\n\n"
                "Tickers:\n{ticker_metadata_json}\n\n"
                "Text:\n{input_text}\n\n"
                "{format_instructions}"
            ),
            input_variables=["input_text"],
            partial_variables={
                "format_instructions": format_instructions,
                "ticker_metadata_json": tickers_json
            }
        )

        chain = prompt | llm | parser

        # Initialize all tickers with null fields first
        for ticker, data in ticker_metadata.items():
            data.setdefault("event_type", None)
            data.setdefault("event_description", None)

        try:
            llm_result = chain.invoke({"input_text": text})

            # Merge LLM results into ticker_metadata, overwriting defaults
            if isinstance(llm_result, dict):
                for ticker, data in llm_result.items():
                    if ticker in ticker_metadata and isinstance(data, dict):
                        ticker_metadata[ticker]["event_type"] = data.get("event_type") or None
                        # if event type is not identified, event description must be null too
                        if data.get("event_type") is None:
                            ticker_metadata[ticker]["event_description"] =  None

            return ticker_metadata

        except Exception as e:
            print(f"[LLM Event Extraction Error] {e}")
            return ticker_metadata 

    def analyse_event(self, post: Dict) -> Dict:
        """
        Include event_type and event_description in ticker_metadata.
        Returns the post with updated ticker_metadata.
        """
        full_text = post["content"]["clean_combined_withurl"]
        ticker_metadata = post.get("ticker_metadata", {})

        updated_ticker_metadata = self._analyse_events_with_llm(full_text, ticker_metadata)
        post["ticker_metadata"] = updated_ticker_metadata

        return post
