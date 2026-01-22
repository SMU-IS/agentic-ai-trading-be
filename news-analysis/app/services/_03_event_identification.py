from typing import Optional

import spacy
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama

from app.core.config import env_config
from app.schemas.event_models import (
    EventResponse,
    LLMEventResult,
    NewsPayload,
)


class EventIdentifierService:
    def __init__(
        self,
        model_type: str = env_config.llm_provider,
        model_name: str = env_config.large_language_model,
        base_url: str = env_config.ollama_base_url,
        spacy_model: str = "en_core_web_sm",
    ):
        self.model_type = model_type
        self.model_name = model_name
        self.base_url = base_url

        self.nlp = spacy.load(spacy_model)

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

    def _analyse_with_spacy(self, text: str) -> Optional[dict]:
        """
        Extracts the semantic 'Who-Did-What'.
        """

        doc = self.nlp(text)

        for token in doc:
            if token.pos_ == "VERB" and token.dep_ == "ROOT":
                subj = next((w.text for w in token.lefts if "subj" in w.dep_), None)
                obj = next((w.text for w in token.rights if "obj" in w.dep_), None)

                if subj and obj:
                    return {
                        "subject": subj,
                        "action": token.lemma_,
                        "target": obj,
                    }
        return None

    async def _analyse_with_llm(self, headline: str, content: str) -> LLMEventResult:
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
            return LLMEventResult(
                is_event=False, event_category="error", confidence=0.0, reasoning=str(e)
            )

    async def process_event(self, payload: NewsPayload) -> EventResponse:
        """
        Workflow: Semantic spaCy extraction -> LLM fallback.
        """
        full_text = f"{payload.headline} {payload.content}"

        # 1. Semantic Analysis
        semantic_info = self._analyse_with_spacy(full_text)
        if semantic_info:
            return EventResponse(
                event_detected=True,
                event_type=semantic_info["action"],
                confidence=0.85,
                method="spacy-nlp",
                summary=f"{semantic_info['subject']} {semantic_info['action']} {semantic_info['target']}",
            )

        # 2. LLM Fallback (Complex inference)
        llm_result = await self._analyse_with_llm(payload.headline, payload.content)

        if llm_result.is_event:
            return EventResponse(
                event_detected=True,
                event_type=llm_result.event_category,
                confidence=llm_result.confidence,
                method=f"llm-{self.model_type}",
                summary=llm_result.reasoning,
            )

        return EventResponse(
            event_detected=False,
            confidence=0.0,
            method="hybrid",
            summary="No significant event identified.",
        )
