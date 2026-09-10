import json, datetime

# Read master dataset (672 days)
master=json.load(open('/root/datasets/btc_etf_flow_dataset.json'))
flows=master['flows_usd_million']
candles={c['date']:c for c in master['candles']}

def iso(d): return datetime.datetime.strptime(d,'%d %b %Y').strftime('%Y-%m-%d')

# Build lookup
flows_by_iso = {}
for d_key in flows:
    flows_by_iso[iso(d_key)] = flows[d_key]

# Read Coinglass tracker (10 days)
d=json.load(open('/root/btc-etf-terminal/public/data/etf-flows.json'))
cg=d.get('ibit_tracker_coinglass',[])

# Calculate cumulative holdings from flows
# IBIT starts from 0 on Jan 11, 2024
ibit_holdings = 0
total_etf_btc = 0

history = []
for d_key in sorted(flows, key=lambda x: datetime.datetime.strptime(x,'%d %b %Y')):
    di = iso(d_key)
    f = flows_by_iso[di]
    c = candles.get(di)
    if not c: continue
    
    # Daily flows in BTC
    ibit_usd = f.get('IBIT') or 0
    ibit_btc = ibit_usd * 1e6 / c['close'] if c['close'] > 0 else 0
    ibit_holdings += ibit_btc
    
    # Total ETF flows in BTC
    total_usd = sum(v for k,v in f.items() if k!='Total' and v is not None)
    total_btc = total_usd * 1e6 / c['close'] if c['close'] > 0 else 0
    total_etf_btc += total_btc
    
    row = {
        "date": di,
        "btcPrice": round(c["close"]),
        "btcMarketCap": round(c["close"]*19_880_000/1e9,1),
        "totalNetFlow": round(sum(v for k,v in f.items() if k!="Total" and v is not None),2)
                        if any(v is not None for k,v in f.items() if k!="Total") else (f.get("Total") or 0.0),
        "IBIT": ibit_usd,
        "perFund": {k:v for k,v in f.items() if k!="Total" and v is not None},
        "ibitHoldingsBtc": round(ibit_holdings),
        "ibitAumUsd": round(ibit_holdings * c["close"] / 1e9, 2),
        "totalEtfBtc": round(total_etf_btc),
        "totalEtfAumUsd": round(total_etf_btc * c["close"] / 1e9, 2),
    }
    
    # If Coinglass has this date, use Coinglass IBIT value (more accurate for recent days)
    for t in cg:
        if t['date'] == di:
            row["IBIT"] = t['IBIT']
            row["perFund"] = t.get('perFund', row["perFund"])
            row["rawBtc"] = t.get('rawBtc')
            break
    
    history.append(row)

# Add any Coinglass dates not in dataset (25, 26 Aug)
existing={f['date'] for f in history}
for t in cg:
    if t['date'] not in existing:
        history.append({
            "date": t['date'],
            "btcPrice": t['btcPrice'],
            "btcMarketCap": t.get('btcMarketCap', 0),
            "totalNetFlow": t.get('totalNetFlow', 0),
            "IBIT": t['IBIT'],
            "perFund": t.get('perFund', {}),
            "rawBtc": t.get('rawBtc'),
            "ibitHoldingsBtc": None,
            "ibitAumUsd": None,
            "totalEtfBtc": None,
            "totalEtfAumUsd": None,
        })

history=sorted(history, key=lambda x: x['date'])

# Final output - NO HARDCODED VALUES
out={
    "generated_at": datetime.datetime.utcnow().isoformat()+"Z",
    "source": "Farside full history + Binance (chart) | Coinglass live scrape (IBIT tracker)",
    "btc_price": history[-1]["btcPrice"],
    "ibit_holdings": round(ibit_holdings),
    "total_etf_btc": round(total_etf_btc),
    "latest_date": history[-1]["date"],
    "flows": history,
    "ibit_tracker_coinglass": cg,
}
json.dump(out, open('/root/btc-etf-terminal/public/data/etf-flows.json','w'))
print(f"Built {len(history)} chart rows")
print(f"IBIT holdings: {round(ibit_holdings):,} BTC = ${round(ibit_holdings * history[-1]['btcPrice'] / 1e9, 2)}B")
print(f"Total ETF: {round(total_etf_btc):,} BTC = ${round(total_etf_btc * history[-1]['btcPrice'] / 1e9, 2)}B")
print(f"Last: {history[-1]['date']}, IBIT: {history[-1]['IBIT']}")
