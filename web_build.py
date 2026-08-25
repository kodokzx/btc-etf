#!/usr/bin/env python3
"""Build public/data/etf-flows.json for btc-etf-terminal from the master dataset.
Full history: all ETF flows + BTC candles -> Net Flow vs BTC Price chart supports 30D/90D/1Y/ALL."""
import json, datetime, os

SRC = "/root/btc-etf/btc_etf_flow_dataset.json"
OUT = "/root/btc-etf-terminal/public/data/etf-flows.json"

data = json.load(open(SRC))
flows = data["flows_usd_million"]          # {"11 Jan 2024": {IBIT:..., Total:...}}
candles = {c["date"]: c for c in data["candles"]}  # "2024-01-11" -> ohlcv

def iso(d): return datetime.datetime.strptime(d, "%d %b %Y").strftime("%Y-%m-%d")

recs = []
for d in sorted(flows, key=lambda x: datetime.datetime.strptime(x, "%d %b %Y")):
    f = flows[d]
    di = iso(d)
    c = candles.get(di)
    px = c["close"] if c else None
    if px is None:
        continue
    recs.append({
        "date": di,
        "btcPrice": round(px),
        "btcMarketCap": round(px * 19_880_000 / 1e9, 1),  # approx supply x price, $B
        # Total net flow: sum of funds present that day (skip None); fall back to Farside total
        "totalNetFlow": round(sum(v for k, v in f.items()
                                  if k not in ("Total",) and v is not None), 2)
                          if any(v is not None for k, v in f.items() if k != "Total")
                          else (f.get("Total") or 0.0),
        "IBIT": f["IBIT"] or 0.0,
        # per-fund map consumed by the Funds chart (skip missing "-")
        "perFund": {k: v for k, v in f.items() if k != "Total" and v is not None},
    })

# latest IBIT BTC change
last = recs[-1]
ibit_btc = round(last["IBIT"] * 1e6 / last["btcPrice"]) if last["btcPrice"] else 0

payload = {
    "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    "source": "Farside Investors (full history) + Binance",
    "btc_price": last["btcPrice"],
    "ibit_holdings": 745786,
    "latest_date": last["date"],
    "latest_ibit_btc": ibit_btc,
    "flows": recs,
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(payload, open(OUT, "w"))
print(f"Wrote {len(recs)} days ({recs[0]['date']} .. {recs[-1]['date']}) -> {OUT}")
