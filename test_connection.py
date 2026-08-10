"""
Quick diagnostic: run this alone (python test_connection.py) to confirm
StockTwits is reachable from your network, without waiting through the
full run.
"""

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

print("Testing: https://api.stocktwits.com/api/2/streams/symbol/AAPL.json\n")

try:
    r = requests.get(
        "https://api.stocktwits.com/api/2/streams/symbol/AAPL.json",
        headers=HEADERS, timeout=10
    )
    if r.status_code == 200:
        data = r.json()
        messages = data.get("messages", [])
        print(f"SUCCESS - status 200, got {len(messages)} messages for AAPL.")
        if messages:
            sample = messages[0]
            body_preview = (sample.get("body") or "")[:100]
            print(f"Sample message: {body_preview}")
        print("\nStockTwits is reachable. Run 'python main.py' for the full pull.")
    else:
        print(f"FAILED - status {r.status_code}. Body preview: {r.text[:200]}")
except requests.exceptions.SSLError as e:
    print(f"SSL ERROR (possibly corporate network SSL inspection): {e}")
except requests.exceptions.ProxyError as e:
    print(f"PROXY ERROR: {e}")
except requests.exceptions.ConnectionError as e:
    print(f"CONNECTION ERROR: {e}")
except Exception as e:
    print(f"UNEXPECTED ERROR: {type(e).__name__}: {e}")
