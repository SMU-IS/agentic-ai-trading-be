from src.config import settings
import requests
from typing import Dict, Any, Optional
from src.models.state import DeepAnalysis

BASE_URL=settings.aggregator_base_url

def post_deepanalysis(deepanalysis: DeepAnalysis) -> Optional[Dict[str, Any]]:
    """
    Post DeepAnalysis to trading/decisions/signals/ endpoint.
    
    Args:
        deepanalysis: DeepAnalysis model instance
    Returns:
        API response JSON or None if failed
    """
    url = f"{BASE_URL}/decisions/signals/"
    
    try:
        response = requests.post(
            url=url,
            json=deepanalysis.model_dump(),  # Converts Pydantic to dict
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        response.raise_for_status()  # Raises exception for 4xx/5xx
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ API POST failed: {e}")
        return None
    
def test_post_deepanalysis() -> None:
    """Test post_deepanalysis() function locally with sample data."""
    
    # Create test DeepAnalysis
    test_signal = DeepAnalysis(
        ticker="AAPL",
        rumor_summary="Apple foldable iPhone rumor confirmed by supply chain",
        credibility="High",
        credibility_reason="Reported by Bloomberg, WSJ, and MacRumors simultaneously. Multiple supply chain sources confirm production ramp.",
        references=[
            "https://bloomberg.com/apple-foldable",
            "https://wsj.com/apple-supply-chain"
        ],
        trade_signal="BUY",
        confidence=9,
        trade_rationale="Positive catalyst + bullish technicals + high credibility. Position for 25% upside target.",
        position_size_pct=1.5,
        stop_loss_pct=10.0,
        target_pct=25.0
    )
    
    print("🚀 Testing post_deepanalysis...")
    print(f"📡 Target URL: {BASE_URL}/decisions/signals/")
    print(f"📊 Sample ticker: {test_signal.ticker}")
    
    # Post to API
    result = post_deepanalysis(test_signal)
    
    if result:
        print("✅ SUCCESS!")
        print(f"📄 Response: {result}")
    else:
        print("❌ FAILED - Check your API server!")
        print("💡 Tips:")
        print("   - Is FastAPI server running? uvicorn main:app --reload")
        print("   - Is MongoDB running? docker ps | grep mongo")
        print("   - Check aggregator_base_url in settings")

# Fix your main block
if __name__ == "__main__":
    test_post_deepanalysis()