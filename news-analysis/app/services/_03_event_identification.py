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
        base_url: str = "http://127.0.0.1:11434"
        or env_config.ollama_base_url,  # Remove hardcoded env
        spacy_model: str = "en_core_web_sm",
    ):
        self.model_type = model_type
        self.model_name = model_name
        self.base_url = base_url

        try:
            self.nlp = spacy.load(spacy_model)
        except OSError:
            print(f"Spacy model '{spacy_model}' not found.")
            from spacy.cli import download

            download(spacy_model)
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
        Extracts semantic SVO (Subject-Verb-Object) but preserves descriptive details and entities.

        Requirements for spaCy:
            1. A Root Verb: The main action.
            2. A Subject (nsubj): Who did it.
            3. An Object (dobj or attr): What they acted upon.

        Requirements for LLM Fallback:
            Use intransitive verbs (Failed by spaCy → LLM Trigger): "Apple stock plummeted."
            Subject: Apple stock | Verb: Plummeted | Object: None
        """

        doc = self.nlp(text)

        for token in doc:
            if token.pos_ == "VERB" and token.dep_ == "ROOT":
                # 1. Expanded Subject/Object Detection
                # Check for active subjects ('nsubj') AND passive subjects ('nsubjpass')
                subjects = [w for w in token.lefts if w.dep_ in ["nsubj", "nsubjpass"]]

                # Check for direct objects ('dobj')
                objects = [w for w in token.rights if w.dep_ in ["dobj", "attr"]]

                if subjects and objects:
                    subj_token = subjects[0]
                    obj_token = objects[0]

                    # 2. Use Noun Chunks for "Meaningful" Text
                    # Grab "strong Q4 earnings", not just "earnings"
                    subj_text = self._get_full_text(doc, subj_token)
                    obj_text = self._get_full_text(doc, obj_token)

                    # 3. Extract High-Value Entities
                    entities = {
                        "organizations": [
                            e.text for e in doc.ents if e.label_ == "ORG"
                        ],
                        "money": [e.text for e in doc.ents if e.label_ == "MONEY"],
                        "dates": [e.text for e in doc.ents if e.label_ == "DATE"],
                        "percentages": [
                            e.text for e in doc.ents if e.label_ == "PERCENT"
                        ],
                    }

                    # 4. Sentiment Hints  e.g. "strong", "weak", "record-breaking"
                    adjectives = [
                        child.text
                        for child in obj_token.children
                        if child.pos_ == "ADJ"
                    ]

                    return {
                        "subject": subj_text,
                        "action": token.lemma_,
                        "target": obj_text,
                        "context": {
                            "entities": entities,
                            "sentiment_words": adjectives,
                        },
                    }
        return None

    def _get_full_text(self, doc, token):
        """
        Helper: Returns the full 'Noun Chunk' containing the token
        (e.g., returns 'strong Q4 earnings' instead of just 'earnings')
        """

        for chunk in doc.noun_chunks:
            if token in chunk:
                return chunk.text

        return token.text

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
                is_event=False, event_category="error", reasoning=str(e)
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
                is_event=True,
                event_type=semantic_info["action"],
                method="spacy-nlp",
                summary=f"{semantic_info}",
            )

        # 2. LLM Fallback (Complex inference)
        llm_result = await self._analyse_with_llm(payload.headline, payload.content)

        if llm_result.is_event:
            return EventResponse(
                is_event=True,
                event_type=llm_result.event_category,
                method=f"llm-{self.model_type}",
                summary=llm_result.reasoning,
            )

        return EventResponse(
            is_event=True,
            event_type="None",
            method="Not Found",
            summary="No significant event identified.",
        )
