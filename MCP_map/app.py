"""
MCP 旅游 Agent 后端 — Flask API
接入 Multi-agent 系统（DeepSeek + 高德API + 文化Agent + 质量迭代）

架构:
  前端 (Leaflet 地图) ←→ Flask API ←→ Multi-agent Orchestrator
                                    ←→ 高德 REST API (路线polyline / POI搜索)

设计原则:
  • Multi-agent Orchestrator 通过 plan_sync() 同步接口调用
  • 地图专用操作 (polyline路线、POI搜索) 直接调高德REST API
  • 前端 HTML/JS/CSS 完全复用，JSON 响应格式不变
"""

import os
import re
import math
import sys
import json
import threading
import requests as http_req
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

# ✅ 配置 sys.path: 优先加载 Multi-agent 目录
sys.path.insert(0, PROJECT_ROOT)
multi_agent_path = os.path.join(PROJECT_ROOT, "Multi-agent")
if multi_agent_path not in sys.path:
    sys.path.insert(0, multi_agent_path)

# ✅ 导入 Multi-agent 编排器（取代旧 orchestrator）
print("[INIT] 导入 Multi-agent 编排器...")
try:
    from multi_agent_orchestrator import TravelPlanningOrchestrator
    print("[INIT] [OK] 使用 Multi-agent 系统（异步多Agent + 文化专项 + 质量迭代）")
except (ImportError, ModuleNotFoundError) as e:
    print(f"[INIT] [ERROR] Multi-agent 导入失败: {e}")
    raise

app = Flask(__name__, static_folder="static", template_folder="templates")

AMAP_KEY = os.environ.get("AMAP_API_KEY", "")

# ========== 全局状态 ==========
_state_lock = threading.RLock()   # 保护 _state 并发读写
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
#  从 Multi-agent 响应中提取前端所需数据
# ================================================================

_RESTAURANT_CATEGORIES = {"餐厅", "美食", "restaurant", "food", "dining"}
_HOTEL_CATEGORIES = {"酒店", "住宿", "民宿", "宾馆", "hotel", "accommodation"}
_FULL_DAY_KEYWORDS = [
    "迪士尼", "环球影城", "游乐园", "主题公园", "野生动物",
    "海洋馆", "水上乐园", "欢乐谷", "方特", "长隆",
    "华侨城", "乐高乐园", "宋城", "横店", "影视城",
    "嘉年华", "动物园", "植物园", "科技馆", "天文台",
]


def _is_full_day_poi(name: str) -> bool:
    """判断POI是否为需要整天游览的景点"""
    return any(kw in name for kw in _FULL_DAY_KEYWORDS)


def _extract_street_number(address: str) -> str:
    """
    从地址字符串里提取"路/街+门牌号"关键部分作为位置唯一键。
    例："虹桥路2381号上海动物园内(西南角)" → "虹桥路2381号"
    """
    m = re.search(r'[\u4e00-\u9fff]{2,}(?:路|街道?|大道|大街|弄|巷)\d+号?', address)
    return m.group(0) if m else ""


def _dedup_same_address_pois(markers: list) -> list:
    """
    对同一门牌号的POI去重，只保留评分最高的一个。
    例："虹桥路2381号上海动物园内(西南角)" 与 "虹桥路2381号上海动物园(西北角)" 只保留一个。
    """
    if len(markers) <= 1:
        return markers

    addr_groups: dict = {}  # street_key -> [marker, ...]
    no_addr = []

    for m in markers:
        key = _extract_street_number(m.get("address", ""))
        if key:
            addr_groups.setdefault(key, []).append(m)
        else:
            no_addr.append(m)

    kept = list(no_addr)
    for key, group in addr_groups.items():
        if len(group) == 1:
            kept.append(group[0])
        else:
            # 评分最高者优先；评分相同取名称最短的（更通用的父景区名）
            best = max(
                group,
                key=lambda x: (float(x.get("rating") or 0), -len(x.get("name", "")))
            )
            removed_names = [x["name"] for x in group if x is not best]
            print(f"[DEDUP-ADDR] 同地址去重({key}): 保留'{best['name']}'，去除{removed_names}")
            kept.append(best)

    for i, k in enumerate(kept):
        k["order"] = i + 1
    return kept


def _dedup_parent_child_pois(markers: list) -> list:
    """
    去除同一景区的子区域重复条目。
    例如："上海动物园-亚洲象馆"、"上海动物园灵长动物区" 均属 "上海动物园"，只保留父景区。

    规则：若当前条目名称以某个已保留条目的名称(≥3字)开头，则视为子区域跳过。
    使用 startswith 而非 in，避免"动物园"误过滤"北京动物园"。
    """
    if len(markers) <= 1:
        return markers
    # 按名称长度升序：短名称(父景区)优先保留
    sorted_markers = sorted(markers, key=lambda m: len(m["name"]))
    kept = []
    for m in sorted_markers:
        name = m["name"]
        is_sub = any(
            len(k["name"]) >= 2 and name.startswith(k["name"]) and name != k["name"]
            for k in kept
        )
        if not is_sub:
            kept.append(m)
    # 重置 order 字段
    for i, k in enumerate(kept):
        k["order"] = i + 1
    return kept


def _dedup_nearby_pois(markers: list, radius_km: float = 0.3) -> list:
    """
    距离去重：同一类别中，距离 ≤ radius_km 的连通组只保留评分最高的一个。
    使用 Union-Find 处理传递性分组（A-B, B-C → {A,B,C} 同组），
    解决"外滩"与"万国建筑博览群"等实际位置几乎重合的景点重复问题。
    """
    if len(markers) <= 1:
        return markers

    n = len(markers)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i in range(n):
        for j in range(i + 1, n):
            d = _haversine_km(
                markers[i].get("lat", 0), markers[i].get("lng", 0),
                markers[j].get("lat", 0), markers[j].get("lng", 0),
            )
            if d <= radius_km:
                union(i, j)

    # Group markers by connected component
    groups: dict = {}
    for i, m in enumerate(markers):
        root = find(i)
        groups.setdefault(root, []).append(m)

    kept = []
    for group in groups.values():
        if len(group) == 1:
            kept.append(group[0])
        else:
            best = max(group, key=lambda x: (float(x.get("rating") or 0), -len(x.get("name", ""))))
            removed_names = [x["name"] for x in group if x is not best]
            print(f"[DEDUP-NEAR] 距离去重({radius_km}km内): 保留'{best['name']}'，去除{removed_names}")
            kept.append(best)

    for i, k in enumerate(kept):
        k["order"] = i + 1
    return kept


def _extract_pois_multiagent(response: dict):
    """从 Multi-agent 响应提取 POI 地图标记"""
    buckets = {"attraction": [], "restaurant": [], "hotel": []}
    seen = set()

    final_plan = response.get("final_plan") or {}
    pois = final_plan.get("pois") or []

    for poi in pois:
        name = poi.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)

        location = poi.get("location") or {}
        lat = location.get("lat", 0)
        lng = location.get("lng", 0)
        if not lat or not lng:
            continue
        # 拒绝无效坐标：中国境内范围大致 lat [18,54], lng [73,135]；(0,0) 是 null island
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            continue
        if abs(lat) < 1 or abs(lng) < 1:
            print(f"[WARN] POI坐标无效(null island): {name} ({lat},{lng})，已跳过")
            continue

        category = (poi.get("category") or "景点").lower()
        if any(k in category for k in _RESTAURANT_CATEGORIES):
            cat = "restaurant"
        elif any(k in category for k in _HOTEL_CATEGORIES):
            cat = "hotel"
        else:
            cat = "attraction"

        marker = {
            "name": name,
            "lng": float(lng),
            "lat": float(lat),
            "type": cat,
            "order": len(buckets[cat]) + 1,
            "address": poi.get("description", ""),
            "rating": poi.get("rating", ""),
            "price": poi.get("price") or "",
            "tel": "",
            "distance": "",
            "opening_hours": poi.get("opening_hours", "") or "",
            "photo_url": (poi.get("images") or [""])[0],
            "is_full_day": poi.get("is_full_day", False) or _is_full_day_poi(name),
        }
        buckets[cat].append(marker)

    # 三轮去重：① 同一门牌号 → ② 名称前缀（子景区）→ ③ 距离近邻（300m内）
    for cat in ("attraction", "restaurant", "hotel"):
        before = len(buckets[cat])
        buckets[cat] = _dedup_same_address_pois(buckets[cat])
        buckets[cat] = _dedup_parent_child_pois(buckets[cat])
        buckets[cat] = _dedup_nearby_pois(buckets[cat], radius_km=0.3)
        removed = before - len(buckets[cat])
        if removed:
            print(f"[DEDUP] {cat}: 去除 {removed} 个重复条目，保留 {len(buckets[cat])} 个")

    return buckets["attraction"], buckets["restaurant"], buckets["hotel"]


def _extract_weather_multiagent(response: dict):
    """从 Multi-agent 响应提取天气，转为前端兼容格式"""
    final_plan = response.get("final_plan") or {}
    weather = final_plan.get("weather") or {}

    if not weather:
        return {}

    # AmapClientAdapter 提供了 forecasts 字段（高德预报格式）
    if "forecasts" in weather:
        return {
            "city": weather.get("city", ""),
            "forecasts": weather["forecasts"],
        }

    # 实况天气：手动构造 forecasts 列表
    return {
        "city": weather.get("city", ""),
        "forecasts": [{
            "dayweather": weather.get("weather", ""),
            "nightweather": weather.get("weather", ""),
            "daytemp": str(weather.get("high_temp", "")),
            "nighttemp": str(weather.get("low_temp", "")),
        }],
    }


# ================================================================
#  自动生成行程规划文本（与游记共享同一数据源）
# ================================================================

def _dist2(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """平方欧氏距离代理，用于相对排序（不需要精确公里数）"""
    return (lat1 - lat2) ** 2 + (lng1 - lng2) ** 2


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两点间 Haversine 距离（公里）"""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))


def _route_output_to_day_attrs(response: dict, attrs: list, days: int) -> list:
    """
    将 RouteAgent 的 optimized_routes 输出转换为 day_attrs 格式。
    day_attrs[i] = 第 i 天的景点 dict 列表（含 lat/lng/is_full_day 等字段）。

    优先用 attrs 查找表补齐完整字段（address/rating/opening_hours 等），
    若 attrs 中找不到则用 RouteAgent 输出的字段做兜底。
    不包含餐厅（餐厅由 _build_plan_text_from_markers 就近追加）。
    """
    day_attrs: list = [[] for _ in range(days)]
    final_plan = response.get("final_plan") or {}
    routes = final_plan.get("optimized_routes") or []
    if not routes:
        # 兜底：RouteAgent 未输出时，按评分均匀分配 attrs
        FALLBACK_MAX = 4
        sorted_attrs = sorted(attrs, key=lambda a: -float(a.get("rating") or 0))
        for idx, attr in enumerate(sorted_attrs):
            d_i = idx % days
            if len(day_attrs[d_i]) < FALLBACK_MAX:
                day_attrs[d_i].append(attr)
        return day_attrs

    # 以景点名称为 key 建立查找表（快速匹配）
    attr_lookup: dict = {a["name"]: a for a in attrs}

    for route_day in routes:
        day_idx = int(route_day.get("day", 1)) - 1
        if day_idx < 0 or day_idx >= days:
            continue
        for poi in route_day.get("pois", []):
            # 跳过 RouteAgent 追加的餐厅条目
            if poi.get("category") in ("餐厅", "restaurant"):
                continue
            name = poi.get("name", "")
            if name in attr_lookup:
                # 用 attrs 完整记录，但以 RouteAgent 判定的 is_full_day 为准
                entry = dict(attr_lookup[name])
                entry["is_full_day"] = poi.get("is_full_day", entry.get("is_full_day", False))
                day_attrs[day_idx].append(entry)
            else:
                # 兜底：将 RouteAgent POI 字段转换为 attr 格式
                day_attrs[day_idx].append({
                    "name": name,
                    "lat": poi.get("latitude", 0),
                    "lng": poi.get("longitude", 0),
                    "is_full_day": poi.get("is_full_day", False),
                    "address": poi.get("address", ""),
                    "rating": poi.get("rating", ""),
                    "type": "attraction",
                    "price": poi.get("cost") or "",
                    "opening_hours": "",
                    "photo_url": "",
                })

    return day_attrs




def _build_plan_text_from_markers(intent: dict, day_attrs: list, rests: list,
                                  weather: dict, response: dict) -> str:
    """
    用 day_attrs/rests（与游记相同的数据源）生成行程面板的 Markdown 文本。
    day_attrs 由 _route_output_to_day_attrs() 从 RouteAgent 输出转换而来。
    始终输出恰好 duration_days 天，解决"10天只显示9天"的问题。
    """
    days = int(intent.get("duration_days", 3) or 3)
    city = intent.get("destination", "目的地")
    final_plan = response.get("final_plan") or {}
    lines = [f"# 🗺️ {city} {days}天旅行规划\n"]

    # 天气摘要
    w_src = final_plan.get("weather") or {}
    if not w_src.get("weather") and weather.get("forecasts"):
        f0 = weather["forecasts"][0]
        w_src = {
            "weather": f0.get("dayweather", ""),
            "high_temp": f0.get("daytemp", ""),
            "low_temp": f0.get("nighttemp", ""),
        }
    if w_src.get("weather"):
        lines.append("## 🌤️ 天气提醒")
        lines.append(f"- 天气: {w_src['weather']}")
        hi, lo = w_src.get("high_temp", ""), w_src.get("low_temp", "")
        if hi or lo:
            lines.append(f"- 气温: {lo}~{hi}℃")
        lines.append("")

    # 文化主题
    theme = final_plan.get("cultural_theme")
    if theme:
        lines.append(f"## 🎭 文化主题\n{theme}\n")

    # 餐厅就近分配（不重复跨天）
    used_rest: set = set()
    lines.append("## 📅 每日行程\n")
    for d_i in range(days):
        lines.append(f"**第 {d_i + 1} 天**\n")
        day_list = day_attrs[d_i] if d_i < len(day_attrs) else []

        for a in day_list:
            badge = " 🎪" if a.get("is_full_day") else ""
            lines.append(f"- {a['name']}{badge}")

        # 选距当天景点中心最近的 1-2 家餐厅
        if rests and day_list:
            c_lat = sum(a.get("lat", 0) for a in day_list) / len(day_list)
            c_lng = sum(a.get("lng", 0) for a in day_list) / len(day_list)
            nearby = sorted(
                ((i, r) for i, r in enumerate(rests) if i not in used_rest),
                key=lambda x: _dist2(c_lat, c_lng, x[1].get("lat", 0), x[1].get("lng", 0)),
            )
            for i, r in nearby[:2]:
                lines.append(f"- 🍽️ {r['name']}")
                used_rest.add(i)

        lines.append("")

    return "\n".join(lines)


# ================================================================
#  自动生成游记框架
# ================================================================

def _auto_journal(intent: dict, day_attrs: list, weather: dict) -> list:
    """
    使用与行程规划共享的 day_attrs 生成游记框架。
    不包含餐厅条目，仅景点 + 每日标题。
    """
    city = intent.get("destination", "")
    entries = []

    for d_i, day_list in enumerate(day_attrs):
        d = d_i + 1
        w = ""
        forecasts = weather.get("forecasts", [])
        if forecasts and d_i < len(forecasts):
            wf = forecasts[d_i]
            w = (f"{wf.get('dayweather', '')}/{wf.get('nightweather', '')}, "
                 f"{wf.get('nighttemp', '')}~{wf.get('daytemp', '')}℃")

        entries.append({
            "id": len(entries) + 1, "day": d, "time": "08:00",
            "title": f"Day {d} — {city}",
            "content": f"[天气] {w}" if w else f"Day {d}",
            "lng": 0, "lat": 0, "photo": "",
        })

        for j, a in enumerate(day_list):
            entries.append({
                "id": len(entries) + 1, "day": d,
                "time": f"{9 + j * 2:02d}:00",
                "title": a["name"],
                "content": f"[地址] {a.get('address', '')}\n\n在这里记录你的感受...",
                "lng": a.get("lng", 0), "lat": a.get("lat", 0),
                "photo": "",
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
    """调用 Multi-agent 编排器规划，返回前端所需的全部地图数据"""
    data = request.json or {}
    query = data.get("query", "")
    if not query:
        print(f"[ERROR] /api/plan: query is required")
        return jsonify({"error": "query is required"}), 400

    print(f"\n{'='*60}")
    print(f"[API] /api/plan: 开始处理请求")
    print(f"[INPUT] query: {query[:100]}")

    try:
        print(f"[STEP 1/4] 创建 Multi-agent 编排器...")
        agent = TravelPlanningOrchestrator()
        print(f"  [OK] 编排器创建成功")

        print(f"[STEP 2/4] 调用 plan_sync()（意图解析 + 多Agent规划）...")
        response = agent.plan_sync(query)
        print(f"  [OK] 规划完成，状态: {response.get('status')}, "
              f"质量评分: {response.get('quality_score', 0):.2f}, "
              f"迭代: {response.get('iterations', 0)}")

        intent = agent.last_intent or {}
        print(f"  [OK] 目的地: {intent.get('destination', 'N/A')}, "
              f"天数: {intent.get('duration_days', 'N/A')}")

        print(f"[STEP 3/4] 提取地图数据...")
        attrs, rests, hotels = _extract_pois_multiagent(response)
        weather = _extract_weather_multiagent(response)

        # 用 RouteAgent 输出构建分天数据（行程规划 + 游记共享同一 day_attrs）
        days = int(intent.get("duration_days", 3) or 3)
        day_attrs = _route_output_to_day_attrs(response, attrs, days)

        plan_text = _build_plan_text_from_markers(intent, day_attrs, rests, weather, response)
        journal = _auto_journal(intent, day_attrs, weather)
        print(f"  [OK] 景点: {len(attrs)}, 餐厅: {len(rests)}, 酒店: {len(hotels)}")
        print(f"  [OK] 天气数据: {bool(weather)}")

        print(f"[STEP 4/4] 计算景点间路线（含 polyline）...")
        # 按行程规划顺序（逐天、天内TSP排序）计算路线，和途经点保持一致
        itinerary_flat = [a for day in day_attrs for a in day]
        routes = []
        if len(itinerary_flat) >= 2:
            city = intent.get("destination", "")
            for i in range(min(len(itinerary_flat) - 1, 8)):
                a, b = itinerary_flat[i], itinerary_flat[i + 1]
                seg = _route_with_polyline(
                    a["lng"], a["lat"], b["lng"], b["lat"],
                    mode="driving", city=city,
                )
                seg["from"] = a["name"]
                seg["to"] = b["name"]
                polyline_pts = seg.get("polyline", [])
                print(f"  [{i+1}] {a['name']} → {b['name']}: "
                      f"{seg.get('distance')}m, polyline={len(polyline_pts)}pts")
                routes.append(seg)

        with _state_lock:
            _state.update({
                "plan_text": plan_text,
                "demands": intent,
                "weather": weather,
                "attractions": attrs,
                "restaurants": rests,
                "hotels": hotels,
                "routes": routes,
                "waypoints": itinerary_flat[:10],
                "journal": journal,
            })

        print(f"[SUCCESS] /api/plan 完成")
        print(f"{'='*60}\n")

        return jsonify({
            "plan_text": plan_text,
            "demands": intent,
            "notice": intent.get("notice") or None,
            "weather": weather,
            "attraction_markers": attrs,
            "restaurant_markers": rests,
            "hotel_markers": hotels,
            "routes": routes,
            "journal": journal,
            # 每天景点顺序（TSP排序），供前端途经点按天切换
            "itinerary_days": [
                [{"name": a["name"], "lat": a["lat"], "lng": a["lng"],
                  "address": a.get("address", ""), "order": j + 1}
                 for j, a in enumerate(day)]
                for day in day_attrs
            ],
        })

    except ValueError as e:
        # 用户输入非旅行需求或目的地无法识别（400 Bad Request）
        print(f"[WARN] 输入无效: {e}")
        print(f"{'='*60}\n")
        return jsonify({"error": str(e)}), 400

    except Exception as e:
        print(f"[ERROR] 规划失败: {e}")
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
    with _state_lock:
        return jsonify(dict(_state))


@app.route("/api/waypoints", methods=["GET"])
def get_waypoints():
    with _state_lock:
        return jsonify(list(_state["waypoints"]))


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
    print("  MCP Travel Agent (Multi-agent backend)")
    print("  http://localhost:5000")
    print("=" * 55)
    print(f"  DEEPSEEK_API_KEY: {'OK (' + ds_key[:8] + '...)' if ds_key else 'MISSING'}")
    print(f"  AMAP_API_KEY:     {'OK (' + api_key[:8] + '...)' if api_key else 'MISSING'}")
    print("=" * 55)
    app.run(debug=True, port=5000)
