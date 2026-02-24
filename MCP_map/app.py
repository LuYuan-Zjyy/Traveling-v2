"""
MCP 旅游 Agent 后端 — Flask API
接入 Langchain 多Agent 系统（DeepSeek + 高德MCP）

架构:
  前端 (Leaflet 地图) ←→ Flask API ←→ Langchain Orchestrator (规划Agent + 文化Agent + 工具Agent)
                                    ←→ 高德 REST API (路线polyline / POI搜索)

设计原则:
  • Langchain Orchestrator 零修改 — 仅通过其公共接口 (plan / last_collected_data / last_intent)
  • 地图专用操作 (polyline路线、POI搜索) 直接调高德REST API
  • 前端 HTML/JS/CSS 完全复用
"""

import os
import sys
import json
import requests as http_req
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

# ✅ 配置 sys.path: 优先加载项目根目录，然后添加 Multi-agent 目录
sys.path.insert(0, PROJECT_ROOT)
multi_agent_path = os.path.join(PROJECT_ROOT, "Multi-agent")
if multi_agent_path not in sys.path:
    sys.path.insert(0, multi_agent_path)

# ✅ 导入配置和编排器
# 注：新系统 (Multi-agent/multi_agent_orchestrator.py) 是异步的，与同步Flask不兼容
# 使用旧的同步系统 (orchestrator/orchestrator.py) 实现
print("[INIT] 配置导入路径...")
try:
    from orchestrator.config import load_config
    from orchestrator.orchestrator import TravelOrchestrator
    print("[INIT] [OK] 使用 orchestrator 系统（同步模式）")
except (ImportError, ModuleNotFoundError) as e:
    print(f"[INIT] [ERROR] orchestrator 导入失败: {e}")
    raise

app = Flask(__name__, static_folder="static", template_folder="templates")

AMAP_KEY = os.environ.get("AMAP_API_KEY", "")

# ========== 全局状态 ==========
_state = {
    "plan_text": "",
    "demands": {},
    "weather": {},
    "attractions": [],
    "restaurants": [],
    "hotels": [],
    "routes": [],
    "waypoints": [],
    "journal": [],
}


# ================================================================
#  高德 REST API 直接调用 (地图专用: polyline / POI搜索)
#  orchestrator 的 AmapTools 不返回 polyline, 地图绘制需要
# ================================================================

def _amap_get(path, params):
    params["key"] = AMAP_KEY
    params["output"] = "json"
    try:
        resp = http_req.get(
            f"https://restapi.amap.com{path}", params=params, timeout=10
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


def _parse_polyline(polyline_str):
    """高德 polyline 字符串 → [[lng, lat], ...]"""
    if not polyline_str:
        return []
    pts = []
    for pair in polyline_str.split(";"):
        parts = pair.split(",")
        if len(parts) == 2:
            try:
                pts.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    return pts


def _route_with_polyline(o_lng, o_lat, d_lng, d_lat, mode="driving", city=""):
    """两点路线规划, 返回含 polyline 的结果"""
    origin = f"{o_lng},{o_lat}"
    destination = f"{d_lng},{d_lat}"
    result = {"distance": 0, "duration": 0, "polyline": []}

    if mode == "walking":
        data = _amap_get("/v3/direction/walking", {
            "origin": origin, "destination": destination
        })
        paths = data.get("route", {}).get("paths", [])
        if paths:
            p = paths[0]
            poly = []
            for step in p.get("steps", []):
                poly.extend(_parse_polyline(step.get("polyline", "")))
            result = {
                "distance": int(p.get("distance", 0)),
                "duration": int(p.get("duration", 0)),
                "polyline": poly,
            }

    elif mode == "bicycling":
        data = _amap_get("/v4/direction/bicycling", {
            "origin": origin, "destination": destination
        })
        paths = data.get("data", {}).get("paths", [])
        if paths:
            p = paths[0]
            poly = []
            for step in p.get("steps", []):
                poly.extend(_parse_polyline(step.get("polyline", "")))
            result = {
                "distance": int(p.get("distance", 0)),
                "duration": int(p.get("duration", 0)),
                "polyline": poly,
            }

    elif mode == "transit":
        data = _amap_get("/v3/direction/transit/integrated", {
            "origin": origin, "destination": destination, "city": city,
        })
        transits = data.get("route", {}).get("transits", [])
        if transits:
            t = transits[0]
            result = {
                "distance": int(data.get("route", {}).get("distance", 0)),
                "duration": int(t.get("duration", 0)),
                "polyline": [[o_lng, o_lat], [d_lng, d_lat]],
                "cost": t.get("cost"),
            }

    else:  # driving
        data = _amap_get("/v3/direction/driving", {
            "origin": origin, "destination": destination, "strategy": "0",
        })
        paths = data.get("route", {}).get("paths", [])
        if paths:
            p = paths[0]
            poly = []
            for step in p.get("steps", []):
                poly.extend(_parse_polyline(step.get("polyline", "")))
            result = {
                "distance": int(p.get("distance", 0)),
                "duration": int(p.get("duration", 0)),
                "polyline": poly,
                "taxi_cost": data.get("route", {}).get("taxi_cost"),
            }

    # ✅ 容错处理：如果 polyline 为空，至少返回起终点连线
    if not result.get("polyline"):
        result["polyline"] = [[o_lng, o_lat], [d_lng, d_lat]]
        print(f"[WARN] API 无 polyline，使用起终点连线: ({o_lng},{o_lat}) → ({d_lng},{d_lat})")
    
    return result


# ================================================================
#  从 orchestrator 收集数据中提取前端所需的标记和天气
# ================================================================

_RESTAURANT_KEYWORDS = {"餐", "饭", "美食", "小吃", "菜", "食", "火锅", "面", "粉"}
_HOTEL_KEYWORDS = {"酒店", "住宿", "民宿", "宾馆", "客栈", "旅馆", "旅社"}


def _classify_poi(keywords: str, types: str):
    kw = keywords.lower()
    if "050000" in types or any(k in kw for k in _RESTAURANT_KEYWORDS):
        return "restaurant"
    if "100000" in types or any(k in kw for k in _HOTEL_KEYWORDS):
        return "hotel"
    return "attraction"


def _extract_pois(collected_data):
    """从 orchestrator 的 collected_data 提取 POI 标记列表"""
    buckets = {"attraction": [], "restaurant": [], "hotel": []}
    seen = set()

    for item in collected_data:
        if item["tool"] not in ("search_pois", "search_around"):
            continue
        result = item["result"]
        if "error" in result:
            continue

        cat = _classify_poi(
            item["args"].get("keywords", ""),
            item["args"].get("types", ""),
        )
        for poi in result.get("pois", []):
            loc = poi.get("location", "")
            if not loc or "," not in loc:
                continue
            name = poi.get("name", "")
            if name in seen:
                continue
            seen.add(name)

            lng_s, lat_s = loc.split(",")
            marker = {
                "name": name,
                "lng": float(lng_s),
                "lat": float(lat_s),
                "type": cat,
                "order": len(buckets[cat]) + 1,
                "address": poi.get("address", ""),
                "rating": poi.get("rating", ""),
                "tel": poi.get("tel", ""),
                "distance": poi.get("distance", ""),
            }
            buckets[cat].append(marker)

    return buckets["attraction"], buckets["restaurant"], buckets["hotel"]


def _extract_weather(collected_data):
    """从 orchestrator 的 collected_data 提取天气信息 (转为前端格式)"""
    for item in collected_data:
        if item["tool"] != "query_weather":
            continue
        r = item["result"]
        if "error" in r:
            continue
        if "casts" in r:
            return {"city": r.get("city", ""), "forecasts": r["casts"]}
        if "weather" in r:
            return {
                "city": r.get("city", ""),
                "forecasts": [{
                    "dayweather": r.get("weather", ""),
                    "daytemp": r.get("temperature", ""),
                    "nighttemp": r.get("temperature", ""),
                }],
            }
    return {}


def _extract_routes_info(collected_data):
    """从 collected_data 提取路线概要 (无 polyline, 仅信息展示)"""
    routes = []
    for item in collected_data:
        if item["tool"] not in ("route_driving", "route_walking", "route_transit"):
            continue
        r = item["result"]
        if "error" in r:
            continue
        args = item["args"]
        route_info = {
            "from": args.get("origin", ""),
            "to": args.get("destination", ""),
            "mode": item["tool"].replace("route_", ""),
        }
        if "routes" in r and r["routes"]:
            first = r["routes"][0]
            route_info["distance"] = int(first.get("distance", 0))
            route_info["duration"] = int(first.get("duration", 0))
        elif "distance" in r:
            route_info["distance"] = int(r.get("distance", 0))
        routes.append(route_info)
    return routes


# ================================================================
#  自动生成游记框架
# ================================================================

def _auto_journal(intent, attractions, weather):
    days = int(intent.get("duration_days", 1) or 1)
    city = intent.get("destination", "")
    entries = []
    per_day = max(1, len(attractions) // days) if attractions else 0
    idx = 0

    for d in range(1, days + 1):
        w = ""
        forecasts = weather.get("forecasts", [])
        if forecasts and d - 1 < len(forecasts):
            wf = forecasts[d - 1]
            w = (f"{wf.get('dayweather', '')}/{wf.get('nightweather', '')}, "
                 f"{wf.get('nighttemp', '')}~{wf.get('daytemp', '')}℃")

        entries.append({
            "id": len(entries) + 1, "day": d, "time": "08:00",
            "title": f"Day {d} — {city}",
            "content": f"[天气] {w}" if w else f"Day {d}",
            "lng": 0, "lat": 0, "photo": "",
        })

        for j in range(per_day):
            if idx >= len(attractions):
                break
            a = attractions[idx]
            entries.append({
                "id": len(entries) + 1, "day": d,
                "time": f"{9 + j * 2:02d}:00",
                "title": a["name"],
                "content": f"[地址] {a.get('address', '')}\n\n在这里记录你的感受...",
                "lng": a.get("lng", 0), "lat": a.get("lat", 0),
                "photo": "",
            })
            idx += 1

        entries.append({
            "id": len(entries) + 1, "day": d, "time": "18:00",
            "title": f"Day {d} 晚餐 & 小结",
            "content": "记录今天的美食和感悟...",
            "lng": 0, "lat": 0, "photo": "",
        })

    return entries


# ================================================================
#  页面
# ================================================================

@app.route("/")
def index():
    return render_template("index.html")


# ================================================================
#  核心 API: Agent 规划 (接入 orchestrator)
# ================================================================

@app.route("/api/plan", methods=["POST"])
def api_plan():
    """调用 orchestrator 主控Agent 规划, 返回前端所需的全部地图数据"""
    data = request.json or {}
    query = data.get("query", "")
    if not query:
        print(f"[ERROR] /api/plan: query is required")
        return jsonify({"error": "query is required"}), 400

    print(f"\n{'='*60}")
    print(f"[API] /api/plan: started processing user query")
    print(f"[INPUT] query: {query[:100]}...")
    
    try:
        print(f"[STEP 1/5] Loading config...")
        config = load_config()
        print(f"  [OK] DeepSeek API Key: {bool(config.deepseek.api_key)}")
        print(f"  [OK] AMap API Key: {bool(config.amap.api_key)}")
        
        print(f"[STEP 2/5] Creating TravelOrchestrator instance...")
        agent = TravelOrchestrator(config=config)
        print(f"  [OK] Agent created successfully")
        
        print(f"[STEP 3/5] Calling agent.plan()...")
        plan_text = agent.plan(query)
        print(f"  [OK] Planning completed, length: {len(plan_text)} chars")

        print(f"[STEP 4/5] Extracting session data...")
        collected = agent.last_collected_data
        intent = agent.last_intent or {}
        print(f"  [OK] Destination: {intent.get('destination', 'N/A')}")
        print(f"  [OK] Days: {intent.get('duration_days', 'N/A')}")
        print(f"  [OK] Tool calls: {len(collected)}")

        print(f"[STEP 5/5] Processing map data...")
        attrs, rests, hotels = _extract_pois(collected)
        weather = _extract_weather(collected)
        journal = _auto_journal(intent, attrs, weather)
        print(f"  [OK] Attractions: {len(attrs)}, Restaurants: {len(rests)}, Hotels: {len(hotels)}")
        print(f"  [OK] Weather data: {bool(weather)}")

        # Generate routes between attractions
        routes = []
        if len(attrs) >= 2:
            city = intent.get("destination", "")
            print(f"[ROUTE] Generating routes between attractions...")
            for i in range(min(len(attrs) - 1, 8)):
                a, b = attrs[i], attrs[i + 1]
                seg = _route_with_polyline(
                    a["lng"], a["lat"], b["lng"], b["lat"],
                    mode="driving", city=city,
                )
                seg["from"] = a["name"]
                seg["to"] = b["name"]
                
                polyline_valid = seg.get("polyline", [])
                print(f"  [{i+1}] {a['name']} -> {b['name']}: "
                      f"{seg.get('distance')}m, {seg.get('duration')}s, "
                      f"polyline={len(polyline_valid)}pts")
                
                routes.append(seg)

        _state.update({
            "plan_text": plan_text,
            "demands": intent,
            "weather": weather,
            "attractions": attrs,
            "restaurants": rests,
            "hotels": hotels,
            "routes": routes,
            "waypoints": attrs[:10],
            "journal": journal,
        })

        print(f"[SUCCESS] /api/plan completed, returning data")
        print(f"{'='*60}\n")
        
        return jsonify({
            "plan_text": plan_text,
            "demands": intent,
            "weather": weather,
            "attraction_markers": attrs,
            "restaurant_markers": rests,
            "hotel_markers": hotels,
            "routes": routes,
            "journal": journal,
        })

    except ImportError as e:
        print(f"[ERROR] Import error: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        return jsonify({"error": f"Import error: {str(e)}"}), 500
        
    except Exception as e:
        print(f"[ERROR] Planning failed: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*60}\n")
        return jsonify({"error": str(e)}), 500


# ================================================================
#  路线规划 API (直接调高德, 含 polyline)
# ================================================================

@app.route("/api/route_plan", methods=["POST"])
def api_route_plan():
    """两点路线规划, 返回真实 polyline"""
    data = request.json or {}
    o = data.get("origin", {})
    d = data.get("destination", {})
    mode = data.get("mode", "driving")
    city = data.get("city", "")

    if not o.get("lng") or not d.get("lng"):
        return jsonify({"error": "origin/destination required"}), 400

    result = _route_with_polyline(
        float(o["lng"]), float(o["lat"]),
        float(d["lng"]), float(d["lat"]),
        mode=mode, city=city,
    )
    result["mode"] = mode
    return jsonify(result)


@app.route("/api/route_plan_multi", methods=["POST"])
def api_route_plan_multi():
    """多点路线规划"""
    data = request.json or {}
    points = data.get("points", [])
    mode = data.get("mode", "driving")
    city = data.get("city", "")
    segments = []

    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        seg = _route_with_polyline(
            float(a["lng"]), float(a["lat"]),
            float(b["lng"]), float(b["lat"]),
            mode=mode, city=city,
        )
        seg["from"] = a.get("name", f"P{i + 1}")
        seg["to"] = b.get("name", f"P{i + 2}")
        seg["mode"] = mode
        segments.append(seg)

    return jsonify({"segments": segments})


# ================================================================
#  高德代理 & POI 搜索
# ================================================================

@app.route("/_AMapService/<path:subpath>")
def amap_service_proxy(subpath):
    """AMap JS API 安全代理"""
    target = f"https://restapi.amap.com/{subpath}"
    try:
        resp = http_req.get(target, params=request.args, timeout=10)
        return resp.content, resp.status_code, {
            "Content-Type": resp.headers.get("Content-Type", "application/json"),
            "Access-Control-Allow-Origin": "*",
        }
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/search_place")
def api_search_place():
    """POI 搜索"""
    kw = request.args.get("keyword", "")
    city = request.args.get("city", "")
    if not kw:
        return jsonify([])

    data = _amap_get("/v3/place/text", {
        "keywords": kw,
        "city": city,
        "citylimit": "true" if city else "false",
        "offset": "8",
    })
    results = []
    for p in data.get("pois", []):
        loc = p.get("location", "")
        if not loc or "," not in loc:
            continue
        lng_s, lat_s = loc.split(",")
        results.append({
            "name": p.get("name", ""),
            "address": p.get("address", ""),
            "longitude": float(lng_s),
            "latitude": float(lat_s),
        })
    return jsonify(results)


# ================================================================
#  状态 / 途经点 / 游记 CRUD
# ================================================================

@app.route("/api/state")
def api_state():
    return jsonify(_state)


@app.route("/api/waypoints", methods=["GET"])
def get_waypoints():
    return jsonify(_state["waypoints"])


@app.route("/api/waypoints", methods=["PUT"])
def update_waypoints():
    _state["waypoints"] = request.json or []
    return jsonify({"ok": True, "count": len(_state["waypoints"])})


@app.route("/api/journal", methods=["GET"])
def get_journal():
    return jsonify(_state["journal"])


@app.route("/api/journal", methods=["PUT"])
def update_journal():
    _state["journal"] = request.json or []
    return jsonify({"ok": True})


@app.route("/api/journal/<int:entry_id>", methods=["PATCH"])
def patch_journal_entry(entry_id):
    patch = request.json or {}
    for e in _state["journal"]:
        if e["id"] == entry_id:
            e.update(patch)
            return jsonify(e)
    return jsonify({"error": "not found"}), 404


@app.route("/api/journal", methods=["POST"])
def add_journal_entry():
    entry = request.json or {}
    entry["id"] = max((e["id"] for e in _state["journal"]), default=0) + 1
    _state["journal"].append(entry)
    return jsonify(entry), 201


@app.route("/api/journal/<int:entry_id>", methods=["DELETE"])
def delete_journal_entry(entry_id):
    _state["journal"] = [e for e in _state["journal"] if e["id"] != entry_id]
    return jsonify({"ok": True})


# ================================================================
#  启动
# ================================================================

if __name__ == "__main__":
    api_key = os.environ.get("AMAP_API_KEY", "")
    ds_key = os.environ.get("DEEPSEEK_API_KEY", "")
    print("=" * 55)
    print("  MCP Travel Agent (orchestrator backend)")
    print("  http://localhost:5000")
    print("=" * 55)
    print(f"  DEEPSEEK_API_KEY: {'OK (' + ds_key[:8] + '...)' if ds_key else 'MISSING'}")
    print(f"  AMAP_API_KEY:     {'OK (' + api_key[:8] + '...)' if api_key else 'MISSING'}")
    print("=" * 55)
    app.run(debug=True, port=5000)
