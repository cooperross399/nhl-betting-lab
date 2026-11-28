import csv, sys, collections
sys.path.insert(0, "web"); sys.path.insert(0, "src")
import build_site_json as b
rows = list(csv.DictReader(open(sys.argv[1])))
print("ledger rows", len(rows), "cols", list(rows[0].keys()))
print("outcomes", collections.Counter(r["outcome"] for r in rows))
def week(d):
    import datetime as dt
    x = dt.date.fromisoformat(d[:10]); return (x - dt.timedelta(days=x.weekday())).isoformat()
def period(d):
    d=d[:10]
    if d < "2026-10-22": return "a 09-29..10-21"
    if d < "2026-11-10": return "b 10-22..11-09"
    if d < "2026-11-25": return "c 11-10..11-24"
    return "d 11-25.."
to = {"won":"win","lost":"loss","push":"push"}
def tally(filt, keyf, label):
    t = collections.defaultdict(lambda: [0,0,0,0.0,0.0,0,0.0])
    seen=set()
    for r in rows:
        res = to.get(r["outcome"]); 
        if res is None: continue
        k=(r["date"][:10], r.get("player_id") or r["player"], r["market"])
        if k in seen: continue
        seen.add(k)
        if filt and not b.meets_due_bars(r["market"], r.get("last_season"), r.get("drought"), r.get("american_odds")): continue
        g = t[keyf(r)]
        g[{"win":0,"loss":1,"push":2}[res]] += 1
        p = b._price(r.get("american_odds"))
        if p is None: continue
        u = b.record_units(p, res, stake=b.prop_stake(p)); f = b.record_units(p, res, stake=1.0)
        g[3]+=u[0]; g[4]+=u[1]; g[5]+=1; g[6]+=f[0]
    print("\n==", label)
    tot=[0,0,0,0.0,0.0,0,0.0]
    for k in sorted(t):
        g=t[k]; print(f"{k:22s} W{g[0]:4d} L{g[1]:4d} P{g[2]:3d}  priced {g[5]:4d}  ladder {g[3]:+8.2f}u on {g[4]:7.2f}  flat1u {g[6]:+8.2f}u")
        for i in range(7): tot[i]+=g[i]
    print(f"{'TOTAL':22s} W{tot[0]:4d} L{tot[1]:4d} P{tot[2]:3d}  priced {tot[5]:4d}  ladder {tot[3]:+8.2f}u on {tot[4]:7.2f}  flat1u {tot[6]:+8.2f}u")
for filt in (False, True):
    tag = "TODAY'S BARS (site)" if filt else "EVERY ENTRY"
    tally(filt, lambda r: period(r["date"]), tag+" by period")
    tally(filt, lambda r: r["market"], tag+" by category")
    tally(filt, lambda r: week(r["date"]), tag+" by week")
# dropped only
t=collections.Counter(); 
for r in rows:
    if to.get(r["outcome"]) and not b.meets_due_bars(r["market"], r.get("last_season"), r.get("drought"), r.get("american_odds")): t[(r["market"], period(r["date"]))]+=1
print("\ndropped by bars", sorted(t.items()))
c = sum(1 for r in rows if to.get(r["outcome"]) and (b._price(r.get("american_odds")) or 0) < -130 and (b._price(r.get("american_odds")) or 0)<0)
print("graded rows priced shorter than -130 (still counted):", c)
