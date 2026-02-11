"""
高德地图 MCP 工具层
封装高德 Web服务 REST API 为 Agent 可调用的工具函数

工具列表:
  1. search_pois       - 关键词搜索 POI (景点/餐厅/酒店等)
  2. search_around      - 周边搜索 POI
  3. geocode            - 地理编码 (地址 → 经纬度)
  4. regeocode          - 逆地理编码 (经纬度 → 地址)
  5. route_driving      - 驾车路线规划
  6. route_transit      - 公交路线规划
  7. route_walking      - 步行路线规划
  8. query_weather      - 天气查询

每个工具都是一个独立函数, 返回结构化 dict, 供 Agent 调用.
同时提供 TOOL_DEFINITIONS 用于 DeepSeek function calling.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional
import time
import urllib3

# 禁用SSL警告（如果遇到SSL证书问题）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class AmapTools:
    """高德地图 REST API 工具集"""

    def __init__(self, api_key: str, base_url: str = "https://restapi.amap.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "TravelAgent/1.0"})
        
        # 配置重试策略
        retry_strategy = Retry(
            total=3,  # 最多重试3次
            backoff_factor=1,  # 重试间隔: 1s, 2s, 4s
            status_forcelist=[429, 500, 502, 503, 504],  # 这些状态码会重试
            allowed_methods=["GET", "POST"],  # 允许重试的HTTP方法
        )
        
        # 配置HTTP适配器
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10
        )
        
        # 为HTTP和HTTPS都配置适配器
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ----------------------------------------------------------
    # 内部: 统一请求
    # ----------------------------------------------------------
    def _get(self, path: str, params: dict) -> dict:
        params["key"] = self.api_key
        params["output"] = "json"
        
        # 手动重试机制 (处理SSL错误)
        max_retries = 3
        retry_delay = 1  # 初始延迟1秒
        
        for attempt in range(max_retries):
            try:
                resp = self.session.get(
                    f"{self.base_url}{path}",
                    params=params,
                    timeout=(5, 15),  # (连接超时, 读取超时)
                    verify=True,  # SSL证书验证
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") != "1":
                    return {"error": data.get("info", "高德API返回错误"), "infocode": data.get("infocode")}
                return data
                
            except requests.exceptions.SSLError as e:
                # SSL错误，尝试重试
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # 指数退避
                    time.sleep(wait_time)
                    continue
                else:
                    # 最后一次重试失败，返回详细错误
                    return {
                        "error": f"SSL连接失败 (已重试{max_retries}次): {str(e)}",
                        "suggestion": "请检查网络连接或SSL配置"
                    }
                    
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
                else:
                    return {"error": f"请求超时 (已重试{max_retries}次): {str(e)}"}
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    time.sleep(wait_time)
                    continue
                else:
                    return {"error": f"连接失败 (已重试{max_retries}次): {str(e)}"}
                    
            except requests.RequestException as e:
                # 其他请求错误，不重试
                return {"error": f"请求高德API失败: {str(e)}"}
        
        # 理论上不会到达这里
        return {"error": "请求失败: 未知错误"}

    # ----------------------------------------------------------
    # 工具 1: 关键词搜索 POI
    # ----------------------------------------------------------
    def search_pois(self, keywords: str, city: str, types: str = "", page_size: int = 10) -> dict:
        """
        关键词搜索 POI (景点/餐厅/酒店等)

        Args:
            keywords: 搜索关键词, 如 "黄梅戏博物馆" "农家乐"
            city: 城市名称, 如 "安庆" "北京"
            types: POI类型码(可选), 如 "110000"(景点) "050000"(餐饮)
            page_size: 返回条数, 默认10
        """
        params = {"keywords": keywords, "city": city, "citylimit": "true", "offset": page_size}
        if types:
            params["types"] = types
        raw = self._get("/v3/place/text", params)
        if "error" in raw:
            return raw

        pois = []
        for p in raw.get("pois", []):
            pois.append({
                "name": p.get("name"),
                "address": p.get("address"),
                "type": p.get("type"),
                "location": p.get("location"),       # "经度,纬度"
                "tel": p.get("tel"),
                "rating": p.get("biz_ext", {}).get("rating", ""),
                "cost": p.get("biz_ext", {}).get("cost", ""),
            })
        return {"count": len(pois), "pois": pois}

    # ----------------------------------------------------------
    # 工具 2: 周边搜索 POI
    # ----------------------------------------------------------
    def search_around(self, location: str, keywords: str = "", types: str = "",
                      radius: int = 3000, page_size: int = 10) -> dict:
        """
        以某个坐标为中心搜索周边 POI

        Args:
            location: 中心坐标 "经度,纬度"
            keywords: 搜索关键词(可选)
            types: POI类型码(可选)
            radius: 搜索半径(米), 默认3000
            page_size: 返回条数
        """
        params = {"location": location, "radius": radius, "offset": page_size}
        if keywords:
            params["keywords"] = keywords
        if types:
            params["types"] = types
        raw = self._get("/v3/place/around", params)
        if "error" in raw:
            return raw

        pois = []
        for p in raw.get("pois", []):
            pois.append({
                "name": p.get("name"),
                "address": p.get("address"),
                "type": p.get("type"),
                "location": p.get("location"),
                "distance": p.get("distance"),
                "rating": p.get("biz_ext", {}).get("rating", ""),
            })
        return {"count": len(pois), "pois": pois}

    # ----------------------------------------------------------
    # 工具 3: 地理编码
    # ----------------------------------------------------------
    def geocode(self, address: str, city: str = "") -> dict:
        """
        地址 → 经纬度坐标

        Args:
            address: 地址文本, 如 "安庆市迎江区人民路"
            city: 城市名(可选, 提高准确度)
        """
        params = {"address": address}
        if city:
            params["city"] = city
        raw = self._get("/v3/geocode/geo", params)
        if "error" in raw:
            return raw

        results = []
        for g in raw.get("geocodes", []):
            results.append({
                "formatted_address": g.get("formatted_address"),
                "location": g.get("location"),
                "province": g.get("province"),
                "city": g.get("city"),
                "district": g.get("district"),
            })
        return {"count": len(results), "geocodes": results}

    # ----------------------------------------------------------
    # 工具 4: 逆地理编码
    # ----------------------------------------------------------
    def regeocode(self, location: str) -> dict:
        """
        经纬度坐标 → 地址

        Args:
            location: 坐标 "经度,纬度"
        """
        params = {"location": location}
        raw = self._get("/v3/geocode/regeo", params)
        if "error" in raw:
            return raw

        regeo = raw.get("regeocode", {})
        return {
            "formatted_address": regeo.get("formatted_address"),
            "province": regeo.get("addressComponent", {}).get("province"),
            "city": regeo.get("addressComponent", {}).get("city"),
            "district": regeo.get("addressComponent", {}).get("district"),
        }

    # ----------------------------------------------------------
    # 工具 5: 驾车路线规划
    # ----------------------------------------------------------
    def route_driving(self, origin: str, destination: str, strategy: int = 0) -> dict:
        """
        驾车路线规划

        Args:
            origin: 起点坐标 "经度,纬度"
            destination: 终点坐标 "经度,纬度"
            strategy: 策略 0=速度优先 1=费用优先 2=距离优先
        """
        params = {"origin": origin, "destination": destination, "strategy": strategy}
        raw = self._get("/v3/direction/driving", params)
        if "error" in raw:
            return raw

        routes = []
        for path in raw.get("route", {}).get("paths", []):
            routes.append({
                "distance": path.get("distance"),          # 米
                "duration": path.get("duration"),          # 秒
                "strategy": path.get("strategy"),
                "toll_distance": path.get("toll_distance"),
                "tolls": path.get("tolls"),                # 收费(元)
            })
        return {"count": len(routes), "routes": routes}

    # ----------------------------------------------------------
    # 工具 6: 公交/地铁路线规划
    # ----------------------------------------------------------
    def route_transit(self, origin: str, destination: str, city: str,
                      strategy: int = 0) -> dict:
        """
        公交/地铁路线规划

        Args:
            origin: 起点坐标 "经度,纬度"
            destination: 终点坐标 "经度,纬度"
            city: 城市名称
            strategy: 策略 0=最快 1=最省 2=最少换乘
        """
        params = {
            "origin": origin, "destination": destination,
            "city": city, "strategy": strategy,
        }
        raw = self._get("/v3/direction/transit/integrated", params)
        if "error" in raw:
            return raw

        transits = []
        for t in raw.get("route", {}).get("transits", [])[:3]:  # 最多3条
            transits.append({
                "cost": t.get("cost"),
                "duration": t.get("duration"),  # 秒
                "walking_distance": t.get("walking_distance"),
                "nightflag": t.get("nightflag"),
            })
        return {
            "distance": raw.get("route", {}).get("distance"),
            "count": len(transits),
            "transits": transits,
        }

    # ----------------------------------------------------------
    # 工具 7: 步行路线规划
    # ----------------------------------------------------------
    def route_walking(self, origin: str, destination: str) -> dict:
        """
        步行路线规划

        Args:
            origin: 起点坐标 "经度,纬度"
            destination: 终点坐标 "经度,纬度"
        """
        params = {"origin": origin, "destination": destination}
        raw = self._get("/v3/direction/walking", params)
        if "error" in raw:
            return raw

        routes = []
        for path in raw.get("route", {}).get("paths", []):
            routes.append({
                "distance": path.get("distance"),  # 米
                "duration": path.get("duration"),  # 秒
            })
        return {"count": len(routes), "routes": routes}

    # ----------------------------------------------------------
    # 工具 8: 天气查询
    # ----------------------------------------------------------
    def query_weather(self, city: str, extensions: str = "base") -> dict:
        """
        天气查询

        Args:
            city: 城市名称或 adcode
            extensions: "base"=实况天气  "all"=预报天气
        """
        params = {"city": city, "extensions": extensions}
        raw = self._get("/v3/weather/weatherInfo", params)
        if "error" in raw:
            return raw

        if extensions == "base":
            lives = raw.get("lives", [])
            if lives:
                w = lives[0]
                return {
                    "city": w.get("city"),
                    "weather": w.get("weather"),
                    "temperature": w.get("temperature"),
                    "winddirection": w.get("winddirection"),
                    "windpower": w.get("windpower"),
                    "humidity": w.get("humidity"),
                    "reporttime": w.get("reporttime"),
                }
            return {"error": "无天气数据"}
        else:
            forecasts = raw.get("forecasts", [])
            if forecasts:
                f = forecasts[0]
                return {
                    "city": f.get("city"),
                    "casts": [
                        {
                            "date": c.get("date"),
                            "week": c.get("week"),
                            "dayweather": c.get("dayweather"),
                            "nightweather": c.get("nightweather"),
                            "daytemp": c.get("daytemp"),
                            "nighttemp": c.get("nighttemp"),
                        }
                        for c in f.get("casts", [])
                    ],
                }
            return {"error": "无预报数据"}

    # ----------------------------------------------------------
    # 调度: 根据工具名和参数调用对应方法
    # ----------------------------------------------------------
    def call_tool(self, tool_name: str, arguments: dict) -> dict:
        """
        统一调度入口, 根据工具名调用对应方法

        Args:
            tool_name: 工具名称 (如 "search_pois", "route_driving")
            arguments: 工具参数字典
        """
        method = getattr(self, tool_name, None)
        if method is None:
            return {"error": f"未知工具: {tool_name}"}
        try:
            return method(**arguments)
        except TypeError as e:
            return {"error": f"工具参数错误: {e}"}


# ==============================================================
# DeepSeek Function Calling 工具定义
# 用于让 DeepSeek 自主决定调用哪些工具
# ==============================================================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_pois",
            "description": "关键词搜索POI(景点、餐厅、酒店、购物等)。根据关键词和城市搜索地点信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {"type": "string", "description": "搜索关键词, 如'黄山风景区' '火锅' '民宿'"},
                    "city": {"type": "string", "description": "城市名称, 如'安庆' '北京' '黄山'"},
                    "types": {"type": "string", "description": "POI类型码(可选), 如'110000'景点 '050000'餐饮 '100000'住宿"},
                    "page_size": {"type": "integer", "description": "返回条数, 默认10", "default": 10},
                },
                "required": ["keywords", "city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_around",
            "description": "以某个坐标为中心搜索周边POI, 适合在确定某景点后搜索附近餐厅、酒店等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "中心坐标, 格式'经度,纬度', 如'117.05,30.53'"},
                    "keywords": {"type": "string", "description": "搜索关键词(可选)"},
                    "types": {"type": "string", "description": "POI类型码(可选)"},
                    "radius": {"type": "integer", "description": "搜索半径(米), 默认3000", "default": 3000},
                },
                "required": ["location"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "geocode",
            "description": "地理编码: 将地址文本转换为经纬度坐标。用于获取某个地点的精确坐标。",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "地址文本, 如'安庆市天柱山' '北京市故宫'"},
                    "city": {"type": "string", "description": "城市名(可选, 提高准确度)"},
                },
                "required": ["address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "route_driving",
            "description": "驾车路线规划: 计算两点间驾车路线的距离和时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "起点坐标 '经度,纬度'"},
                    "destination": {"type": "string", "description": "终点坐标 '经度,纬度'"},
                    "strategy": {"type": "integer", "description": "策略: 0速度优先 1费用优先 2距离优先", "default": 0},
                },
                "required": ["origin", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "route_transit",
            "description": "公共交通路线规划: 计算两点间公交/地铁路线。",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "起点坐标 '经度,纬度'"},
                    "destination": {"type": "string", "description": "终点坐标 '经度,纬度'"},
                    "city": {"type": "string", "description": "城市名称"},
                },
                "required": ["origin", "destination", "city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "route_walking",
            "description": "步行路线规划: 计算两点间步行路线的距离和时间。",
            "parameters": {
                "type": "object",
                "properties": {
                    "origin": {"type": "string", "description": "起点坐标 '经度,纬度'"},
                    "destination": {"type": "string", "description": "终点坐标 '经度,纬度'"},
                },
                "required": ["origin", "destination"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_weather",
            "description": "查询城市天气(实况或预报), 帮助用户了解目的地天气情况。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称, 如'安庆' '北京'"},
                    "extensions": {"type": "string", "description": "'base'实况天气 'all'预报天气", "default": "all"},
                },
                "required": ["city"],
            },
        },
    },
]

