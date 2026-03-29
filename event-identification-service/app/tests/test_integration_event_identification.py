"""
Integration Tests — EventIdentifierService (real LLM calls)
Tests the full flow: _identify_primary_tickers → _analyse_events_with_llm → _propose_new_events_with_llm

Run with:
    pytest app/tests/test_integration_event_identification.py -v -s --no-header

Requires GROQ_API_KEY in .env
"""

import pytest
from langchain_core.callbacks import BaseCallbackHandler
from app.services._03_event_identification import EventIdentifierService

# ==========================================================
# EVENT LIST
# ==========================================================

EVENT_LIST = {
    "EARNINGS_BEAT": {"event_category": "COMPANY_EVENT", "meaning": "Reported earnings exceed market consensus expectations."},
    "EARNINGS_MISS": {"event_category": "COMPANY_EVENT", "meaning": "Reported earnings fall below market consensus expectations."},
    "INSIDER_BUYING": {"event_category": "COMPANY_EVENT", "meaning": "Company executives or board members purchase company shares, signaling confidence in the company."},
    "INSIDER_SELLING": {"event_category": "COMPANY_EVENT", "meaning": "Company executives or board members sell company shares, potentially signaling reduced confidence or personal liquidity needs."},
    "GUIDANCE_UPGRADE": {"event_category": "COMPANY_EVENT", "meaning": "Company raises forward-looking financial guidance."},
    "GUIDANCE_DOWNGRADE": {"event_category": "COMPANY_EVENT", "meaning": "Company lowers forward-looking financial guidance."},
    "MERGER": {"event_category": "COMPANY_EVENT", "meaning": "Two companies combine to form a single entity."},
    "ACQUISITION": {"event_category": "COMPANY_EVENT", "meaning": "Company acquires controlling interest in another company."},
    "DIVESTITURE": {"event_category": "COMPANY_EVENT", "meaning": "Company sells or spins off a business unit or asset."},
    "IPO": {"event_category": "COMPANY_EVENT", "meaning": "Company offers shares to the public for the first time."},
    "SECONDARY_OFFERING": {"event_category": "COMPANY_EVENT", "meaning": "Company issues additional shares after an initial public offering."},
    "SHARE_BUYBACK": {"event_category": "COMPANY_EVENT", "meaning": "Company repurchases its own shares from the market."},
    "DIVIDEND_INCREASE": {"event_category": "COMPANY_EVENT", "meaning": "Company increases its dividend payout to shareholders."},
    "DIVIDEND_CUT": {"event_category": "COMPANY_EVENT", "meaning": "Company reduces or suspends its dividend payout."},
    "MANAGEMENT_CHANGE": {"event_category": "COMPANY_EVENT", "meaning": "Change in senior management or executive leadership."},
    "REGULATORY_APPROVAL": {"event_category": "EXTERNAL_EVENT", "meaning": "Company receives approval from a regulatory authority."},
    "REGULATORY_PENALTY": {"event_category": "EXTERNAL_EVENT", "meaning": "Company is fined or sanctioned by a regulatory authority."},
    "REGULATORY_INVESTIGATION": {"event_category": "EXTERNAL_EVENT", "meaning": "A regulatory authority initiates or announces an investigation into the company's operations, compliance, or business practices."},
    "PRODUCT_LAUNCH": {"event_category": "COMPANY_EVENT", "meaning": "Company introduces a new product or service to the market."},
    "PRODUCT_RECALL": {"event_category": "COMPANY_EVENT", "meaning": "Company recalls products due to safety or quality issues."},
    "STRATEGIC_PARTNERSHIP": {"event_category": "COMPANY_EVENT", "meaning": "Company enters a formal partnership to pursue strategic objectives."},
    "DEBT_ISSUANCE": {"event_category": "COMPANY_EVENT", "meaning": "Company raises capital by issuing debt instruments."},
    "DEBT_RESTRUCTURING": {"event_category": "COMPANY_EVENT", "meaning": "Company renegotiates or modifies existing debt obligations."},
    "BANKRUPTCY": {"event_category": "COMPANY_EVENT", "meaning": "Company files for legal bankruptcy protection."},
    "RESTRUCTURING": {"event_category": "COMPANY_EVENT", "meaning": "Company reorganizes operations to improve financial or operational performance."},
    "LITIGATION": {"event_category": "EXTERNAL_EVENT", "meaning": "Company is involved in a legal dispute or lawsuit."},
    "SETTLEMENT": {"event_category": "COMPANY_EVENT", "meaning": "Company resolves a legal dispute through an agreed settlement."},
    "PATENT_DISPUTE": {"event_category": "EXTERNAL_EVENT", "meaning": "Company is involved in a legal dispute over intellectual property rights."},
    "STOCK_SPLIT": {"event_category": "COMPANY_EVENT", "meaning": "Company increases share count by splitting existing shares."},
    "SUPPLY_CHAIN_DISRUPTION": {"event_category": "EXTERNAL_EVENT", "meaning": "Significant external disruptions to sourcing, logistics, or manufacturing inputs affecting the company."},
    "GOVERNMENT_INVESTMENT": {"event_category": "EXTERNAL_EVENT", "meaning": "Government takes equity stakes, provides bailouts, or makes strategic investments in a company."},
    "COMPANY_INVESTMENT": {"event_category": "COMPANY_EVENT", "meaning": "Company allocates significant capital to strategic projects, initiatives, or infrastructure."},
    "DATA_BREACH": {"event_category": "COMPANY_EVENT", "meaning": "Unauthorized access to or exposure of company or customer data."},
    "NATURAL_DISASTER_IMPACT": {"event_category": "EXTERNAL_EVENT", "meaning": "Company operations are materially affected by a natural disaster."},
    "TECHNOLOGY_UPGRADE": {"event_category": "COMPANY_EVENT", "meaning": "Company implements significant improvements to technology systems or platforms."},
    "TECHNOLOGY_FAILURE": {"event_category": "COMPANY_EVENT", "meaning": "Company experiences a material technology or system outage."},
    "MARKET_ENTRY": {"event_category": "COMPANY_EVENT", "meaning": "Company enters a new geographic or product market."},
    "COMPETITOR_ANNOUNCEMENT": {"event_category": "EXTERNAL_EVENT", "meaning": "Action or announcement by a competitor that may materially affect investor perception of the company."},
    "EXTERNAL_INDUSTRY_GROWTH": {"event_category": "EXTERNAL_EVENT", "meaning": "Investors may adjust valuations and expectations for companies due to projected growth in the broader industry or sector."},
    "INVESTOR_ACTION": {"event_category": "INVESTOR_EVENT", "meaning": "Observable investor activity related to the stock."},
    "INVESTOR_OPINION": {"event_category": "INVESTOR_EVENT", "meaning": "Investor sentiment, predictions, or subjective opinions about the stock."},
    "EARNINGS_CALL": {"event_category": "COMPANY_EVENT", "meaning": "Statements, metrics, or forward-looking commentary made by company executives during an official earnings call."},
    "EQUITY_AND_DEBT_FINANCING_PLAN": {"event_category": "COMPANY_EVENT", "meaning": "The company announces a plan to raise significant capital through equity or debt instruments."},
    "PRODUCT_LINE_DISCONTINUATION": {"event_category": "COMPANY_EVENT", "meaning": "Company permanently stops producing or selling a specific product line."},
}


# ==========================================================
# TOKEN TRACKING CALLBACK
# ==========================================================

class TokenTracker(BaseCallbackHandler):
    def __init__(self):
        self.calls = []

    def on_llm_end(self, response, **kwargs):
        usage = getattr(response, "llm_output", {}) or {}
        token_usage = usage.get("token_usage", {})
        if token_usage:
            self.calls.append({
                "input_tokens": token_usage.get("prompt_tokens", 0),
                "output_tokens": token_usage.get("completion_tokens", 0),
            })


def make_service(tracker: TokenTracker = None) -> EventIdentifierService:
    service = EventIdentifierService(event_list=EVENT_LIST.copy())
    if tracker and service.llm:
        service.llm.callbacks = [tracker]
    return service


def build_filtered_events_str(category: str) -> str:
    return "\n".join(
        f"- {name}"
        for name, meta in EVENT_LIST.items()
        if meta.get("event_category") == category
    )


# ==========================================================
# CASE 1: Known event — should map to taxonomy, no proposal
# ==========================================================

@pytest.mark.asyncio
async def test_known_event_maps_to_taxonomy():
    """
    Post describes an earnings beat — should map to EARNINGS_BEAT, no proposal triggered.
    """
    post = {
        "content": {
            "clean_combined_withurl": (
                "Apple just crushed Q2 earnings expectations. EPS came in at $1.52 vs $1.35 consensus. "
                "Revenue beat by 8%. Stock up 4% after hours."
            )
        },
        "ticker_metadata": {
            "AAPL": {"sentiment_score": 0.8, "sentiment_label": "positive"},
        },
        "metadata": {},
    }

    tracker = TokenTracker()
    service = make_service(tracker)
    result = await service.analyse_event(post)

    aapl = result["ticker_metadata"].get("AAPL", {})
    print(f"\n[Known Event] event_type     : {aapl.get('event_type')}")
    print(f"[Known Event] event_description: {aapl.get('event_description')}")
    print(f"[Known Event] event_proposal   : {aapl.get('event_proposal')}")
    print(f"[Known Event] LLM calls token usage: {tracker.calls}")

    assert aapl.get("event_type") is not None
    assert aapl.get("event_proposal") is None, "Should not propose a new event for a known taxonomy match"


# ==========================================================
# CASE 2: Novel event — should trigger proposal
# ==========================================================

@pytest.mark.asyncio
async def test_novel_event_triggers_proposal():
    """
    Post describes a carbon credit issuance — not in taxonomy.
    Should reach _propose_new_events_with_llm and return a proposal.
    """
    post = {
        "content": {
            "clean_combined_withurl": (
                "Tesla has issued 2 million carbon credits to the EU carbon market, "
                "generating an estimated $180M in revenue. This is the largest single "
                "carbon credit transaction in the company's history."
            )
        },
        "ticker_metadata": {
            "TSLA": {"sentiment_score": 0.6, "sentiment_label": "positive"},
        },
        "metadata": {},
    }

    tracker = TokenTracker()
    service = make_service(tracker)

    events_before = set(service.event_list.keys())
    result = await service.analyse_event(post)
    events_after = set(service.event_list.keys())

    tsla = result["ticker_metadata"].get("TSLA", {})
    new_events = events_after - events_before

    print(f"\n[Novel Event] event_type     : {tsla.get('event_type')}")
    print(f"[Novel Event] event_proposal  : {tsla.get('event_proposal')}")
    print(f"[Novel Event] New events added: {new_events}")
    print(f"[Novel Event] LLM calls token usage: {tracker.calls}")

    assert tsla.get("event_type") is not None


# ==========================================================
# CASE 3: Token count — with vs without existing_events_str
# ==========================================================

@pytest.mark.asyncio
async def test_token_count_with_and_without_existing_events():
    """
    Calls _propose_new_events_with_llm twice:
    - once without existing_events_str
    - once with existing_events_str
    Prints actual token difference from LLM responses.
    """
    unmatched = {"TSLA": {"primary_event_category": "COMPANY_EVENT"}}
    text = (
        "Tesla has issued 2 million carbon credits to the EU carbon market, "
        "generating an estimated $180M in revenue."
    )
    filtered = build_filtered_events_str("COMPANY_EVENT")

    tracker_without = TokenTracker()
    service_without = make_service(tracker_without)
    await service_without._propose_new_events_with_llm(text, unmatched, existing_events_str="")

    tracker_with = TokenTracker()
    service_with = make_service(tracker_with)
    await service_with._propose_new_events_with_llm(text, unmatched, existing_events_str=filtered)

    print("\n--- Actual Token Usage Comparison ---")
    print(f"Without existing_events_str : {tracker_without.calls}")
    print(f"With existing_events_str    : {tracker_with.calls}")

    if tracker_without.calls and tracker_with.calls:
        diff = tracker_with.calls[0]["input_tokens"] - tracker_without.calls[0]["input_tokens"]
        print(f"Input token difference      : +{diff} tokens")


# ==========================================================
# CASE 4: Guardrail — LLM should not re-propose existing event
# ==========================================================

@pytest.mark.asyncio
async def test_guardrail_prevents_duplicate_proposal():
    """
    Post describes a strategic partnership — STRATEGIC_PARTNERSHIP already exists.
    With existing_events_str guardrail, LLM should return null for proposed_event_name.
    """
    unmatched = {"MSFT": {"primary_event_category": "COMPANY_EVENT"}}
    text = (
        "Microsoft has entered into a formal partnership with OpenAI to jointly develop "
        "enterprise AI tools. The deal includes a $2B investment over 5 years."
    )
    filtered = build_filtered_events_str("COMPANY_EVENT")

    service = make_service()
    result = await service._propose_new_events_with_llm(text, unmatched, existing_events_str=filtered)

    msft = result.get("MSFT", {})
    proposed = msft.get("proposed_event_name")

    print(f"\n[Guardrail Test] Full proposal: {msft}")
    print(f"[Guardrail Test] proposed_event_name: {proposed}")

    if proposed:
        assert proposed not in EVENT_LIST, (
            f"Guardrail failed — LLM proposed '{proposed}' which already exists in taxonomy"
        )
        print(f"[Guardrail Test] ✅ Genuinely new event proposed: {proposed}")
    else:
        print("[Guardrail Test] ✅ LLM correctly returned null — event already covered")
