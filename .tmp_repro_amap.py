import os
import sys
sys.path.insert(0, r"d:/VScode python/Traveling-v2/Multi-agent")
from tools.amap_tools import AmapTools
from multi_agent_orchestrator import AmapClientAdapter

key = os.environ.get("AMAP_API_KEY", "")
print("has_key", bool(key))
if not key:
    raise SystemExit(0)

t = AmapTools(api_key=key)
a = AmapClientAdapter(t)
print("geo", a.geocode("安庆"))

ks = ["景点", "餐厅", "酒店", "古镇", "湖泊", "公园", "博物馆", "文化街区"]
for k in ks:
    r = t.search_pois(keywords=k, city="安庆", page_size=10, page=1)
    print(k, "error" if "error" in r else "ok", r.get("error", ""), "count", len(r.get("pois", [])))

ps = a.search_pois("安庆", 30.53, 117.11, ks, 25)
print("adapter_total", len(ps))
