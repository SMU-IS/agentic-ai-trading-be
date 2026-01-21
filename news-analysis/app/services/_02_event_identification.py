import re
from typing import Optional

from app.core.config import env_config
from app.core.constant import DEFAULT_RULES
from app.schemas.event_models import (
    EventResponse,
    LLMEventResult,
    NewsPayload,
)
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama


class EventIdentifierService:
    def __init__(
        self,
        model_type: str = env_config.llm_provider,
        model_name: str = env_config.large_language_model,
        base_url: str = env_config.ollama_base_url,
    ):
        self.model_type = model_type
        self.model_name = model_name
        self.base_url = base_url
        self.rules = DEFAULT_RULES

    def _get_llm(self):
        """
        Factory method to initialise the LLM connection.
        """

        if self.model_type == env_config.llm_provider:
            return ChatOllama(
                model=self.model_name,
                base_url=self.base_url,
                temperature=0,
                format="json",
            )
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")

    def _analyse_with_rules(self, text: str) -> Optional[tuple[str, float]]:
        """
        Fast regex check for keywords.
        """

        text_lower = text.lower()
        for event_type, patterns in self.rules.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return event_type, 0.95

        return None

    async def _analyse_with_llm(self, headline: str, content: str) -> LLMEventResult:
        """
        Complex inference using LLM
        """

        llm = self._get_llm()
        parser = JsonOutputParser(pydantic_object=LLMEventResult)

        prompt_template = PromptTemplate(
            template="""
            You are a financial analyst AI. Analyze the following news for significant investment events.

            Headline: {headline}
            Snippet: {content}

            {format_instructions}
            """,
            input_variables=["headline", "content"],
            partial_variables={"format_instructions": parser.get_format_instructions()},
        )

        chain = prompt_template | llm | parser

        try:
            result = chain.invoke({"headline": headline, "content": content})
            return LLMEventResult(**result)

        except Exception as e:
            print(f"LLM Error: {e}")
            return LLMEventResult(
                is_event=False, event_category="error", confidence=0.0, reasoning=str(e)
            )

    async def process_event(self, payload: NewsPayload) -> EventResponse:
        """
        Main public method: Orchestrates Rule-based -> LLM fallback.
        """

        full_text = f"{payload.headline} {payload.content}"

        # 1. Rule-based Approach
        rule_result = self._analyse_with_rules(full_text)
        if rule_result:
            event_type, confidence = rule_result
            return EventResponse(
                event_detected=True,
                event_type=event_type,
                confidence=confidence,
                method="rule-based",
                summary=f"Detected via keywords: {event_type}",
            )

        # 2. LLLM
        llm_result = await self._analyse_with_llm(payload.headline, payload.content)

        if llm_result.is_event:
            return EventResponse(
                event_detected=True,
                event_type=llm_result.event_category,
                confidence=llm_result.confidence,
                method=f"llm-{self.model_type}",
                summary=llm_result.reasoning,
            )

        # 3. No Event
        return EventResponse(
            event_detected=False,
            confidence=0.0,
            method="hybrid",
            summary="No significant event identified.",
        )
