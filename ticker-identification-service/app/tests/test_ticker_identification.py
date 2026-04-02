"""
Unit Tests — TickerIdentificationService

All LLM, spacy, and yfinance calls are mocked.
No real API calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ==========================================================
# Fixtures
# ==========================================================

@pytest.fixture
def service():
    """Service with all external dependencies mocked."""
    with patch("app.services._02_ticker_identification.ChatGroq"), \
         patch("app.services._02_ticker_identification.JsonOutputParser"), \
         patch("app.services._02_ticker_identification.spacy"):

        from app.services._02_ticker_identification import TickerIdentificationService

        svc = TickerIdentificationService(
            cleaned_tickers={
                "apple": {"ticker": "AAPL", "title": "Apple Inc.", "type": "stock"},
                "microsoft": {"ticker": "MSFT", "title": "Microsoft Corp.", "type": "stock"},
            },
            alias_to_canonical={"apple inc": "apple"},
        )

        # Mock nlp to return no NER entities by default
        mock_doc = MagicMock()
        mock_doc.ents = []
        svc.nlp = MagicMock(return_value=mock_doc)

        # Mock LLM to return empty by default (override per test as needed)
        svc._extract_company_ticker_llm = AsyncMock(return_value=[])

        yield svc


# ==========================================================
# Initialization
# ==========================================================

def test_service_initialization(service):
    """Service loads, ticker_to_title and ticker_to_canonical are built correctly."""
    assert service is not None
    assert service.ticker_to_title["AAPL"] == "Apple Inc."
    assert service.ticker_to_canonical["AAPL"] == "apple"
    assert service.ticker_to_canonical["MSFT"] == "microsoft"


# ==========================================================
# _normalize_company() / _remove_suffix()
# ==========================================================

def test_normalize_company(service):
    assert service._normalize_company("Apple Inc.") == "appleinc"


def test_remove_suffix_inc(service):
    assert service._remove_suffix("Apple Inc.") == "Apple"


def test_remove_suffix_corp(service):
    assert service._remove_suffix("Microsoft Corp") == "Microsoft"


def test_remove_suffix_no_suffix(service):
    assert service._remove_suffix("Apple") == "Apple"


# ==========================================================
# build_canonical_to_aliases()
# ==========================================================

def test_build_canonical_to_aliases(service):
    result = service.build_canonical_to_aliases({"apple inc": "apple", "aapl": "apple"})
    assert "apple" in result
    assert "apple inc" in result["apple"]
    assert "aapl" in result["apple"]


# ==========================================================
# update_alias_mapping()
# ==========================================================

def test_update_alias_mapping_adds_new(service):
    """New alias not yet in mapping → added, new_alias_count incremented."""
    before = service.new_alias_count
    service.update_alias_mapping("Apple Incorporated", "apple")
    assert service.new_alias_count == before + 1
    assert "apple incorporated" in service.alias_to_canonical or \
           service._normalize_company(service._remove_suffix("Apple Incorporated")) in service.alias_to_canonical


def test_update_alias_mapping_skips_duplicate(service):
    """Alias already in mapping → not added again."""
    service.update_alias_mapping("Apple Inc", "apple")  # adds it
    count_after_first = service.new_alias_count
    service.update_alias_mapping("Apple Inc", "apple")  # duplicate — skipped
    assert service.new_alias_count == count_after_first


def test_update_alias_mapping_skips_same_as_canonical(service):
    """Alias that normalizes to the canonical itself → skipped."""
    before = service.new_alias_count
    service.update_alias_mapping("apple", "apple")
    assert service.new_alias_count == before


# ==========================================================
# get_aliases()
# ==========================================================

def test_get_aliases(service):
    service.canonical_to_aliases = {"apple": ["apple inc", "aapl"]}

    result = service.get_aliases(["AAPL"])

    assert "AAPL" in result
    assert result["AAPL"]["OfficialName"] == "Apple Inc."
    assert "apple inc" in result["AAPL"]["Aliases"]


def test_get_aliases_unknown_ticker(service):
    """Ticker not in mapping → OfficialName empty, Aliases empty."""
    result = service.get_aliases(["UNKNOWN"])
    assert result["UNKNOWN"]["OfficialName"] == ""
    assert result["UNKNOWN"]["Aliases"] == []


# ==========================================================
# classify_ticker()
# ==========================================================

def test_classify_ticker_stock(service):
    with patch("app.services._02_ticker_identification.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = {"quoteType": "EQUITY"}
        result = service.classify_ticker("AAPL")
    assert result == "stock"


def test_classify_ticker_etf(service):
    with patch("app.services._02_ticker_identification.yf") as mock_yf:
        mock_yf.Ticker.return_value.info = {"quoteType": "ETF"}
        result = service.classify_ticker("SPY")
    assert result == "etf"


def test_classify_ticker_exception_returns_none(service):
    with patch("app.services._02_ticker_identification.yf") as mock_yf:
        mock_yf.Ticker.side_effect = Exception("Network error")
        result = service.classify_ticker("AAPL")
    assert result is None


# ==========================================================
# _extract_company_ticker_llm()
# ==========================================================

@pytest.mark.asyncio
async def test_extract_company_ticker_llm_returns_validated_list(service):
    """LLM returns valid list → validated and returned."""
    chain_mock = AsyncMock(return_value=[{"company_name": "Apple Inc.", "ticker": "aapl"}])
    service.llm = MagicMock()
    service.parser = MagicMock()

    with patch("app.services._02_ticker_identification.PromptTemplate") as mock_pt:
        mock_pt.return_value.__or__ = MagicMock(return_value=MagicMock(
            __or__=MagicMock(return_value=chain_mock)
        ))
        # Re-call the real method (bypass our AsyncMock fixture override)
        from app.services._02_ticker_identification import TickerIdentificationService
        result = await TickerIdentificationService._extract_company_ticker_llm(service, "Apple earnings")

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_extract_company_ticker_llm_no_llm_returns_empty(service):
    """LLM not initialized → returns empty list immediately."""
    service.llm = None
    # Re-call real method
    from app.services._02_ticker_identification import TickerIdentificationService
    result = await TickerIdentificationService._extract_company_ticker_llm(service, "some text")
    assert result == []


# ==========================================================
# extract_tickers()
# ==========================================================

@pytest.mark.asyncio
async def test_extract_tickers_via_ner(service):
    """NER finds ORG matching cleaned ticker → ticker returned in metadata."""
    mock_ent = MagicMock()
    mock_ent.text = "Apple"
    mock_ent.label_ = "ORG"
    service.nlp.return_value.ents = [mock_ent]
    service._extract_company_ticker_llm = AsyncMock(return_value=[])

    result = await service.extract_tickers("Apple announced earnings")

    assert "AAPL" in result
    assert result["AAPL"]["type"] == "stock"


@pytest.mark.asyncio
async def test_extract_tickers_via_alias(service):
    """NER finds ORG matching alias → resolves to canonical ticker."""
    mock_ent = MagicMock()
    mock_ent.text = "Apple Inc"
    mock_ent.label_ = "ORG"
    service.nlp.return_value.ents = [mock_ent]
    service._extract_company_ticker_llm = AsyncMock(return_value=[])

    result = await service.extract_tickers("Apple Inc announced earnings")

    assert "AAPL" in result


@pytest.mark.asyncio
async def test_extract_tickers_via_regex(service):
    """$AAPL in text → picked up by regex even with no NER."""
    service.nlp.return_value.ents = []
    service._extract_company_ticker_llm = AsyncMock(return_value=[])

    result = await service.extract_tickers("$AAPL is up today")

    assert "AAPL" in result


@pytest.mark.asyncio
async def test_extract_tickers_via_llm(service):
    """LLM returns ticker in known mapping → added to metadata."""
    service.nlp.return_value.ents = []
    service._extract_company_ticker_llm = AsyncMock(return_value=[
        {"company_name": "Apple Inc.", "ticker": "AAPL"}
    ])

    result = await service.extract_tickers("Big tech company announced results")

    assert "AAPL" in result


@pytest.mark.asyncio
async def test_extract_tickers_non_stock_filtered(service):
    """Ticker of type 'etf' → filtered out, not included in results."""
    service.cleaned_tickers["spdr"] = {"ticker": "SPY", "title": "SPDR S&P 500", "type": "etf"}
    service.ticker_to_title["SPY"] = "SPDR S&P 500"
    service.ticker_to_canonical["SPY"] = "spdr"
    service.nlp.return_value.ents = []
    service._extract_company_ticker_llm = AsyncMock(return_value=[])

    result = await service.extract_tickers("$SPY is down")

    assert "SPY" not in result


@pytest.mark.asyncio
async def test_extract_tickers_empty_text(service):
    """No entities, no regex match, no LLM result → empty dict."""
    service.nlp.return_value.ents = []
    service._extract_company_ticker_llm = AsyncMock(return_value=[])

    result = await service.extract_tickers("nothing relevant here")

    assert result == {}


# ==========================================================
# process_post()
# ==========================================================

@pytest.mark.asyncio
async def test_process_post_with_provided_ticker(service):
    """metadata.ticker provided → skips NER/LLM, uses provided ticker directly."""
    post = {
        "id": "p1",
        "content": {"clean_combined_withurl": ""},
        "metadata": {"ticker": ["AAPL"]},
    }

    result = await service.process_post(post)

    assert "ticker_metadata" in result
    assert "AAPL" in result["ticker_metadata"]
    service._extract_company_ticker_llm.assert_not_called()


@pytest.mark.asyncio
async def test_process_post_provided_ticker_not_in_mapping(service):
    """Provided ticker not in mapping → skipped, ticker_metadata not set."""
    post = {
        "id": "p1",
        "content": {"clean_combined_withurl": ""},
        "metadata": {"ticker": ["ZZZZ"]},
    }

    result = await service.process_post(post)

    assert "ticker_metadata" not in result or result.get("ticker_metadata") == {}


@pytest.mark.asyncio
async def test_process_post_fallback_to_extraction(service):
    """No provided ticker → falls back to extract_tickers."""
    service.nlp.return_value.ents = []
    service._extract_company_ticker_llm = AsyncMock(return_value=[
        {"company_name": "Apple Inc.", "ticker": "AAPL"}
    ])

    post = {
        "id": "p1",
        "content": {"clean_combined_withurl": "Apple reported strong earnings"},
        "metadata": {},
    }

    result = await service.process_post(post)

    assert "ticker_metadata" in result
    assert "AAPL" in result["ticker_metadata"]


@pytest.mark.asyncio
async def test_process_post_provided_ticker_as_string(service):
    """metadata.ticker as plain string → treated as single ticker."""
    post = {
        "id": "p1",
        "content": {"clean_combined_withurl": ""},
        "metadata": {"ticker": "AAPL"},
    }

    result = await service.process_post(post)

    assert "AAPL" in result.get("ticker_metadata", {})


@pytest.mark.asyncio
async def test_process_post_provided_ticker_invalid_type_treated_as_empty(service):
    """metadata.ticker is an int (invalid type) → falls back to empty, uses extract_tickers."""
    service.nlp.return_value.ents = []
    service._extract_company_ticker_llm = AsyncMock(return_value=[])

    post = {
        "id": "p1",
        "content": {"clean_combined_withurl": "nothing"},
        "metadata": {"ticker": 123},  # not str or list → treated as empty
    }

    result = await service.process_post(post)

    assert "ticker_metadata" not in result


@pytest.mark.asyncio
async def test_process_post_provided_ticker_non_stock_skipped(service):
    """Provided ticker exists but type is etf → filtered out, ticker_metadata not set."""
    service.cleaned_tickers["spdr"] = {"ticker": "SPY", "title": "SPDR S&P 500", "type": "etf"}
    service.ticker_to_title["SPY"] = "SPDR S&P 500"
    service.ticker_to_canonical["SPY"] = "spdr"

    post = {
        "id": "p1",
        "content": {"clean_combined_withurl": ""},
        "metadata": {"ticker": ["SPY"]},
    }

    result = await service.process_post(post)

    assert "ticker_metadata" not in result


# ==========================================================
# __init__ — LLM initialization failure
# ==========================================================

def test_init_llm_failure_sets_none():
    """ChatGroq raises on init → llm and parser set to None."""
    with patch("app.services._02_ticker_identification.ChatGroq", side_effect=Exception("API error")), \
         patch("app.services._02_ticker_identification.JsonOutputParser"), \
         patch("app.services._02_ticker_identification.spacy"):

        from app.services._02_ticker_identification import TickerIdentificationService

        svc = TickerIdentificationService(cleaned_tickers={}, alias_to_canonical={})

        assert svc.llm is None
        assert svc.parser is None


# ==========================================================
# _update_cleaned_entry() — missing canon / type fetch
# ==========================================================

def test_update_cleaned_entry_unknown_ticker_returns_none(service):
    """Ticker not in ticker_to_canonical → returns None."""
    result = service._update_cleaned_entry("ZZZZ")
    assert result is None


def test_update_cleaned_entry_fetches_type_when_missing(service):
    """Type missing from cleaned entry → calls classify_ticker and stores result."""
    service.cleaned_tickers["newco"] = {"ticker": "NEW", "title": "New Co"}
    service.ticker_to_canonical["NEW"] = "newco"
    service.classify_ticker = MagicMock(return_value="stock")

    result = service._update_cleaned_entry("NEW")

    assert result == "stock"
    assert service.cleaned_tickers["newco"]["type"] == "stock"
    assert service.new_type_count == 1


# ==========================================================
# _extract_company_ticker_llm() — edge cases
# ==========================================================

@pytest.mark.asyncio
async def test_extract_company_ticker_llm_string_result_parsed(service):
    """LLM returns a JSON string → parsed into list."""
    chain_mock = AsyncMock(return_value='[{"company_name": "Apple", "ticker": "AAPL"}]')
    service.llm = MagicMock()
    service.parser = MagicMock()

    with patch("app.services._02_ticker_identification.PromptTemplate") as mock_pt:
        mock_chain = MagicMock()
        mock_chain.ainvoke = chain_mock
        mock_pt.return_value.__or__ = MagicMock(return_value=MagicMock(
            __or__=MagicMock(return_value=mock_chain)
        ))
        from app.services._02_ticker_identification import TickerIdentificationService
        result = await TickerIdentificationService._extract_company_ticker_llm(service, "text")

    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_extract_company_ticker_llm_dict_result_wrapped(service):
    """LLM returns a dict → wrapped into a single-element list."""
    chain_mock = AsyncMock(return_value={"company_name": "Apple", "ticker": "AAPL"})
    service.llm = MagicMock()
    service.parser = MagicMock()

    with patch("app.services._02_ticker_identification.PromptTemplate") as mock_pt:
        mock_chain = MagicMock()
        mock_chain.ainvoke = chain_mock
        mock_pt.return_value.__or__ = MagicMock(return_value=MagicMock(
            __or__=MagicMock(return_value=mock_chain)
        ))
        from app.services._02_ticker_identification import TickerIdentificationService
        result = await TickerIdentificationService._extract_company_ticker_llm(service, "text")

    assert isinstance(result, list)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_extract_company_ticker_llm_all_retries_fail(service):
    """All LLM attempts fail → returns empty list after LLM_MAX_RETRIES."""
    service.llm = MagicMock()
    service.parser = MagicMock()

    with patch("app.services._02_ticker_identification.PromptTemplate") as mock_pt, \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(side_effect=Exception("LLM down"))
        mock_pt.return_value.__or__ = MagicMock(return_value=MagicMock(
            __or__=MagicMock(return_value=mock_chain)
        ))
        from app.services._02_ticker_identification import TickerIdentificationService
        result = await TickerIdentificationService._extract_company_ticker_llm(service, "text")

    assert result == []


@pytest.mark.asyncio
async def test_extract_company_ticker_llm_skips_non_dict_items(service):
    """LLM returns list with non-dict items → those items skipped."""
    chain_mock = AsyncMock(return_value=["not_a_dict", {"company_name": "Apple", "ticker": "AAPL"}])
    service.llm = MagicMock()
    service.parser = MagicMock()

    with patch("app.services._02_ticker_identification.PromptTemplate") as mock_pt:
        mock_chain = MagicMock()
        mock_chain.ainvoke = chain_mock
        mock_pt.return_value.__or__ = MagicMock(return_value=MagicMock(
            __or__=MagicMock(return_value=mock_chain)
        ))
        from app.services._02_ticker_identification import TickerIdentificationService
        result = await TickerIdentificationService._extract_company_ticker_llm(service, "text")

    # Only the dict item should be in the result
    assert len(result) == 1
    assert result[0]["ticker"] == "AAPL"


# ==========================================================
# extract_tickers() — dedup name_identified paths
# ==========================================================

@pytest.mark.asyncio
async def test_extract_tickers_ner_dedup_name_identified(service):
    """Same ticker found twice via NER → name_identified deduped."""
    mock_ent1 = MagicMock()
    mock_ent1.text = "Apple"
    mock_ent1.label_ = "ORG"
    mock_ent2 = MagicMock()
    mock_ent2.text = "Apple Inc"  # resolves via alias → same AAPL
    mock_ent2.label_ = "ORG"
    service.nlp.return_value.ents = [mock_ent1, mock_ent2]
    service._extract_company_ticker_llm = AsyncMock(return_value=[])

    result = await service.extract_tickers("Apple and Apple Inc both reported earnings")

    assert "AAPL" in result
    # Both names should be present without duplicates
    assert len(result["AAPL"]["name_identified"]) == len(set(result["AAPL"]["name_identified"]))


@pytest.mark.asyncio
async def test_extract_tickers_regex_dedup_name_identified(service):
    """$AAPL appears twice in text → name_identified not duplicated."""
    service.nlp.return_value.ents = []
    service._extract_company_ticker_llm = AsyncMock(return_value=[])

    result = await service.extract_tickers("$AAPL up today, $AAPL hits ATH")

    assert "AAPL" in result
    assert result["AAPL"]["name_identified"].count("$AAPL") == 1


@pytest.mark.asyncio
async def test_extract_tickers_llm_dedup_name_identified(service):
    """LLM returns ticker already found by NER → company_name appended once."""
    mock_ent = MagicMock()
    mock_ent.text = "Apple"
    mock_ent.label_ = "ORG"
    service.nlp.return_value.ents = [mock_ent]
    service._extract_company_ticker_llm = AsyncMock(return_value=[
        {"company_name": "Apple Inc.", "ticker": "AAPL"},
        {"company_name": "Apple Inc.", "ticker": "AAPL"},  # duplicate
    ])

    result = await service.extract_tickers("Apple earnings beat")

    assert "AAPL" in result
    assert result["AAPL"]["name_identified"].count("Apple Inc.") == 1


@pytest.mark.asyncio
async def test_extract_tickers_llm_non_stock_filtered(service):
    """LLM returns ticker whose type is not 'stock' → not added to metadata."""
    service.cleaned_tickers["spdr"] = {"ticker": "SPY", "title": "SPDR ETF", "type": "etf"}
    service.ticker_to_title["SPY"] = "SPDR ETF"
    service.ticker_to_canonical["SPY"] = "spdr"
    service.nlp.return_value.ents = []
    service._extract_company_ticker_llm = AsyncMock(return_value=[
        {"company_name": "SPDR", "ticker": "SPY"}
    ])

    result = await service.extract_tickers("SPDR ETF is trending")

    assert "SPY" not in result
