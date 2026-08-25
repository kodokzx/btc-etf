#!/usr/bin/env python3
"""Daily updater: append newest BTC ETF flows + closed BTC candle to dataset, push to GitHub.
Append-only: never re-scrapes history. Runs from cron; exits 0 quietly when nothing new."""
import json, re, subprocess, datetime, os, sys

REPO = "/root/btc-etf"
MD = os.path.join(REPO, "btc_etf_flow_dataset.md")
JS = os.path.join(REPO, "btc_etf_flow_dataset.json")
COLS = ["IBIT","FBTC","BITB","ARKB","BTCO","EZBC","BRRR","HODL","BTCW","MSBT","GBTC","BTC","Total"]

def sh(cmd, **kw): return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kw)

# --- 1. fetch full flow table (jina proxy bypasses Cloudflare) ---
r = sh(["curl","-s","-L","--max-time","90",
        "https://r.jina.ai/https://farside.co.uk/bitcoin-etf-flow-all-data/"])
if r.returncode != 0 or len(r.stdout) < 5000:
    print(f"WARN: flow fetch failed ({r.returncode}, {len(r.stdout)}b)"); sys.exit(1)

# rows are markdown pipes: | 11 Jan 2024 | 111.7 | ... | 655.3 |
recs = {}
for line in r.stdout.split("\n"):
    m = re.match(r"\|\s*(\d{2} \w{3} 20\d{2})\s*\|(.+)\|", line.strip())
    if not m: continue
    cells = [c.strip() for c in m.group(2).split("|")]
    if len(cells) != 13: continue
    vals = []
    for c in cells:
        if c == "-" or c == "": vals.append(None)
        else:
            neg = c.startswith("(")
            v = float(c.strip("()").replace(",",""))
            vals.append(-v if neg else v)
    s12 = sum(x for x in vals[:12] if x is not None)
    if vals[12] is None or abs(s12 - vals[12]) <= 0.5:
        recs[m.group(1)] = vals

if not recs:
    print("WARN: no rows parsed"); sys.exit(1)

# --- 2. fetch candles (closed only) ---
kr = sh(["curl","-s","--max-time","60",
         "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=1000"])
kdata = json.loads(kr.stdout)
now_ms = datetime.datetime.utcnow().timestamp() * 1000
candles = {}
for k in kdata:
    if int(k[6]) < now_ms:
        d = datetime.datetime.utcfromtimestamp(k[0]/1000).strftime("%d %b %Y")
        candles[d] = k

new_days = [d for d in sorted(recs, key=lambda x: datetime.datetime.strptime(x,"%d %b %Y"))
            if recs[d][0] is not None or recs[d][12] not in (None, 0.0)]

md_text = open(MD).read()
existing = set(re.findall(r"^\| (\d{2} \w{3} 20\d{2}) \|", md_text, re.M))

added = [d for d in new_days if d not in existing]
if not added:
    print("No new data."); sys.exit(0)

def fmt(x): return "-" if x is None else f"{x:.1f}"

with open(MD, "a") as fp:
    for d in added:
        v = recs[d]
        k = candles.get(d)
        if k:
            row = (f"| {d} | {fmt(v[0])} | {fmt(v[12])} | "
                   f"{float(k[1]):,.0f} | {float(k[2]):,.0f} | {float(k[3]):,.0f} | "
                   f"{float(k[4]):,.0f} | {float(k[5]):,.1f} |\n")
            app = (f"| {d} | " + " | ".join(fmt(x) for x in v) + " |\n")
        else:
            row = (f"| {d} | {fmt(v[0])} | {fmt(v[12])} | - | - | - | - | - |\n")
            app = (f"| {d} | " + " | ".join(fmt(x) for x in v) + " |\n")
        fp.write(row)
        with open(REPO + "/.appendix_tmp", "a") as fa: fa.write(app)

# appendix rows go into the all-funds section
if os.path.exists(REPO + "/.appendix_tmp"):
    app = open(REPO + "/.appendix_tmp").read()
    os.remove(REPO + "/.appendix_tmp")
    txt = open(MD).read()
    open(MD,"w").write(txt.rstrip("\n") + "\n" + app)

# --- 3. update JSON snapshot ---
flows = {d: dict(zip(COLS, v)) for d, v in recs.items()}
old = json.load(open(JS)) if os.path.exists(JS) else {"candles": []}
old["flows_usd_million"] = flows
old.setdefault("meta", {})["updated"] = datetime.datetime.utcnow().strftime("%Y-%m-%d")
cd = old.get("candles", [])
have = {c["date"] for c in cd}
for d, k in candles.items():
    iso = datetime.datetime.strptime(d,"%d %b %Y").strftime("%Y-%m-%d")
    if iso not in have:
        cd.append({"date":iso,"open":float(k[1]),"high":float(k[2]),
                   "low":float(k[3]),"close":float(k[4]),"volume_btc":float(k[5])})
old["candles"] = sorted(cd, key=lambda c: c["date"])
json.dump(old, open(JS,"w"), indent=1)

print(f"Added {len(added)} day(s): {', '.join(added)}")

# --- 4. refresh 90D/1Y/ALL summary ---
def summarize(sel, label):
    ib = [flows[d]["IBIT"] for d in sel if flows[d]["IBIT"] is not None]
    tot = [flows[d]["Total"] for d in sel if flows[d]["Total"] is not None]
    cdates = sorted(candles)
    first_c = datetime.datetime.strptime(sel[0], "%d %b %Y").strftime("%Y-%m-%d")
    last_c = datetime.datetime.strptime(sel[-1], "%d %b %Y").strftime("%Y-%m-%d")
    cw = [candles[c] for c in cdates if first_c <= c <= last_c]
    chg = (cw[-1]["close"] / cw[0]["open"] - 1) * 100 if cw else 0
    return ({"label": label, "trading_days": len(sel),
             "ibit_total_M": round(sum(ib), 1), "all_etf_total_M": round(sum(tot), 1),
             "btc_change_pct": round(chg, 1), "btc_start": cw[0]["open"], "btc_end": cw[-1]["close"],
             "best_day": max(sel, key=lambda d: flows[d]["IBIT"] or -9e9),
             "worst_day": min(sel, key=lambda d: flows[d]["IBIT"] or 9e9)})

ds_all = sorted(flows, key=lambda x: datetime.datetime.strptime(x, "%d %b %Y"))
periods = {"90D": summarize(ds_all[-90:], "last 90 trading days"),
           "1Y": summarize(ds_all[-260:], "last 260 trading days"),
           "ALL": summarize(ds_all, "since 11 Jan 2024")}

def fmt_period(key):
    s = periods[key]
    sign = "+" if s["ibit_total_M"] >= 0 else ""
    sign_a = "+" if s["all_etf_total_M"] >= 0 else ""
    return "\n".join([
        f"## {key} — {s['label']}", "",
        f"- Hari perdagangan: {s['trading_days']}",
        f"- IBIT net flow: **{sign}${s['ibit_total_M']/1000:.2f} miliar**",
        f"- Semua ETF BTC net flow: **{sign_a}${s['all_etf_total_M']/1000:.2f} miliar**",
        f"- Pergerakan BTC: ${s['btc_start']:,.0f} → ${s['btc_end']:,.0f} ({s['btc_change_pct']:+.1f}%)",
        f"- Hari terbaik IBIT: {s['best_day']} (+${flows[s['best_day']]['IBIT']:.1f} jt)",
        f"- Hari terburuk IBIT: {s['worst_day']} (${flows[s['worst_day']]['IBIT']:.1f} jt)", ""])

summary_md = "\n".join([
    "# Ringkasan Periodik — BTC ETF Flow (dari dataset lengkap)", "",
    f"Diperbarui: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} · Sumber: Farside + Binance · Append-only dari dataset utama.", "",
    fmt_period("90D"), fmt_period("1Y"), fmt_period("ALL"),
    "---", "Catatan: angka diperbarui otomatis oleh cron harian."])
open(os.path.join(REPO, "ringkasan-90d-1y-all.md"), "w").write(summary_md)
print("Summary refreshed.")
