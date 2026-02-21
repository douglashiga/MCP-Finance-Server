import requests
import json

# The subagent's confirmed working URL for ABB
url = "https://www.avanza.se/_api/market-option-future-forward-list/filter-options?anyUnderlyingOrderbookIds=5447&instrumentType=OPTION"

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.avanza.se/borshandlade-produkter/optioner-terminer/lista.html?ui=5447",
    "X-Requested-With": "XMLHttpRequest"
}

print(f"Mimicking browser GET: {url}")
resp = requests.get(url, headers=headers)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    count = data.get("totalNumberOfInstruments", 0)
    print(f"Total instruments: {count}")
    instruments = data.get("instruments", [])
    print(f"Found {len(instruments)} in this response")
    if instruments:
        for i in range(min(3, len(instruments))):
             print(f"- {instruments[i].get('name')} (ID: {instruments[i].get('orderbookId')})")
else:
    print(f"Error: {resp.text}")
