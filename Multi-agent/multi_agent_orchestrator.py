"""
多Agent编排器 - 主协调层
管理所有Agent的执行流程、迭代反馈和结果融合
"""

import os
import re
import asyncio
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# 加载环境变量
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"), override=True)

# 多城市分隔符
_CITY_SEP = re.compile(r'[、，,/＋+&]')


def _first_city(destination: str) -> str:
    """
    从可能的多城市字符串中提取第一个城市名。
    "上海、苏州" → "上海"，"北京+天津" → "北京"，"上海" → "上海"
    如果无法分割或只有一个部分，直接原样返回。
    """
    if not destination:
        return destination
    parts = [p.strip() for p in _CITY_SEP.split(destination) if p.strip()]
    return parts[0] if parts else destination

from core.planning_context import PlanningContext, UserIntent, POI
from agents.data_collection_agent import DataCollectionAgent
from agents.culture_agent import CultureAgent
from agents.quality_eval_agent import QualityEvalAgent
from agents.budget_agent import BudgetAgent
from Route.route_planning_agent import RouteOptimizationAgent
from ui_modules import UIResponseBuilder
from tools.amap_tools import AmapTools
from tools.deepseek_client import DeepSeekClient
from tools.search_tools import get_search_tool


# ================================================================
#  Amap 适配器 - 将 AmapTools 接口适配为 DataCollectionAgent 期望的接口
# ================================================================

class AmapClientAdapter:
    """
    将 AmapTools 的接口适配为 DataCollectionAgent 期望的接口
    DataCollectionAgent 期望:
      geocode(location) -> {"lat": float, "lng": float} | None
      search_pois(location, lat, lng, poi_types) -> List[POI]
      get_weather(location, date) -> dict
    """

    def __init__(self, amap_tools: AmapTools):
        self._tools = amap_tools

    def geocode(self, location: str) -> Optional[Dict[str, float]]:
        """地址 → {"lat": float, "lng": float}"""
        # 多城市输入（如"上海、苏州"）只取第一个城市进行地理编码
        city = _first_city(location)
        if city != location:
            print(f"[AmapAdapter] geocode: 多城市输入 '{location}' → 使用 '{city}'")
        result = self._tools.geocode(address=city)
        if "error" in result:
            return None
        geocodes = result.get("geocodes", [])
        if not geocodes:
            return None
        loc_str = geocodes[0].get("location", "")
        if not loc_str or "," not in loc_str:
            return None
        lng_s, lat_s = loc_str.split(",", 1)
        try:
            return {"lat": float(lat_s), "lng": float(lng_s)}
        except ValueError:
            return None

    def search_pois(self, location: str, lat: float, lng: float,
                    poi_types: List[str] = None, page_size: int = 8) -> List[POI]:
        """搜索 POI → List[POI 对象]"""
        # 多城市输入只取第一个城市，避免 Amap city 参数无效导致返回莫名城市结果
        city_param = _first_city(location)
        if city_param != location:
            print(f"[AmapAdapter] search_pois: 多城市输入 '{location}' → city='{city_param}'")
        keywords_list = poi_types or ["景点", "餐厅", "酒店"]
        all_pois: List[POI] = []
        seen_names: set = set()
        poi_id = 0

        # Amap 每页最多 25 条；需要更多条目时自动翻页
        AMAP_MAX_PER_PAGE = 25
        per_page = min(AMAP_MAX_PER_PAGE, page_size)
        num_pages = max(1, (page_size + AMAP_MAX_PER_PAGE - 1) // AMAP_MAX_PER_PAGE)

        for kw in keywords_list:
            for page_num in range(1, num_pages + 1):
                result = self._tools.search_pois(
                    keywords=kw, city=city_param,
                    page_size=per_page, page=page_num,
                )
                if "error" in result:
                    break
                batch = result.get("pois", [])
                if not batch:
                    break  # 没有更多结果了
                for p in batch:
                    name = p.get("name", "")
                    if not name or name in seen_names:
                        continue
                    seen_names.add(name)

                    loc_str = p.get("location", "")
                    if loc_str and "," in loc_str:
                        lng_s, lat_s = loc_str.split(",", 1)
                        try:
                            poi_lng, poi_lat = float(lng_s), float(lat_s)
                        except ValueError:
                            poi_lng, poi_lat = lng, lat
                    else:
                        poi_lng, poi_lat = lng, lat

                    if "餐" in kw or "美食" in kw or "饭" in kw:
                        category = "餐厅"
                    elif "酒店" in kw or "住宿" in kw or "民宿" in kw:
                        category = "酒店"
                    else:
                        category = "景点"

                    rating_str = p.get("rating", "")
                    try:
                        rating = float(rating_str) if rating_str else None
                    except (ValueError, TypeError):
                        rating = None

                    cost_str = p.get("cost", "")
                    try:
                        price = float(cost_str) if cost_str else None
                    except (ValueError, TypeError):
                        price = None

                    tel = p.get("tel", "")
                    address = p.get("address", "")
                    desc_parts = [address]
                    if tel:
                        desc_parts.append(f"Tel: {tel}")
                    description = " | ".join(p for p in desc_parts if p)

                    photo_url = p.get("photo_url", "")
                    opening_time = p.get("opening_time", "")

                    poi_id += 1
                    all_pois.append(POI(
                        id=f"amap_{poi_id:03d}",
                        name=name,
                        category=category,
                        location={"lat": poi_lat, "lng": poi_lng},
                        rating=rating,
                        price=price,
                        opening_hours=opening_time or None,
                        description=description,
                        images=[photo_url] if photo_url else [],
                    ))

        return all_pois

    def get_weather(self, location: str, date: Optional[str] = None) -> Dict[str, Any]:
        """查询天气 → weather dict"""
        # 优先获取预报天气（all），前端格式兼容更好
        result = self._tools.query_weather(city=location, extensions="all")
        if "error" not in result:
            casts = result.get("casts", [])
            if casts:
                c = casts[0]
                return {
                    "city": result.get("city", location),
                    "weather": c.get("dayweather", ""),
                    "high_temp": c.get("daytemp", ""),
                    "low_temp": c.get("nighttemp", ""),
                    "wind": "",
                    "air_quality": "未知",
                    "forecasts": casts,  # 保留完整预报供 app.py 使用
                }

        # 降级：实况天气
        result = self._tools.query_weather(city=location, extensions="base")
        if "error" not in result:
            return {
                "city": result.get("city", location),
                "weather": result.get("weather", ""),
                "high_temp": result.get("temperature", ""),
                "low_temp": result.get("temperature", ""),
                "humidity": result.get("humidity", ""),
                "wind": f"{result.get('winddirection', '')} {result.get('windpower', '')}",
                "air_quality": "未知",
            }

        return {"city": location}


class TravelPlanningOrchestrator:
    """
    多Agent编排器

    执行流程：
    1. 初始化 - 创建PlanningContext和所有Agent
    2. 执行循环 - 最多5次迭代
       - 第1次：DataCollectionAgent → CultureAgent → RouteOptimizationAgent → BudgetAgent
       - 后续：根据QualityEvalAgent反馈，让相关Agent改进
    3. 质量评估 - QualityEvalAgent评分，是否继续迭代
    4. 结果融合 - 组合所有Agent输出
    5. 响应生成 - 转换为7个UI模块
    """

    MAX_ITERATIONS = 5
    QUALITY_THRESHOLD = 0.75

    def __init__(self):
        """初始化编排器，自动加载真实 API 客户端"""
        # 初始化真实 Amap 客户端
        amap_key = os.environ.get("AMAP_API_KEY", "")
        _amap_raw = AmapTools(api_key=amap_key) if amap_key else None
        amap_client = AmapClientAdapter(_amap_raw) if _amap_raw else None
        self._amap_raw = _amap_raw   # 保留原始 AmapTools 用于精确名称搜索
        if amap_client:
            print("[Orchestrator] Amap API 已接入（真实数据模式）")
        else:
            print("[Orchestrator] 未配置 AMAP_API_KEY，使用 mock 数据")

        # 初始化 DeepSeek 客户端（用于意图解析）
        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
        deepseek_base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        deepseek_model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self._llm = DeepSeekClient(
            api_key=deepseek_key,
            base_url=deepseek_base,
            model=deepseek_model,
        ) if deepseek_key else None
        if self._llm:
            print("[Orchestrator] DeepSeek LLM 已接入（自然语言解析）")
        else:
            print("[Orchestrator] 未配置 DEEPSEEK_API_KEY，意图解析降级为关键词提取")

        # 搜索引擎工具（优先 Bing，没有 Key 则 DuckDuckGo）
        self._search_tool = get_search_tool()

        self.data_collection_agent = DataCollectionAgent(amap_client=amap_client)
        self.culture_agent = CultureAgent(
            llm_client=self._llm,
            search_tool=self._search_tool,
        )
        self.route_agent = RouteOptimizationAgent()
        self.quality_eval_agent = QualityEvalAgent()
        self.budget_agent = BudgetAgent()

        self.execution_history: List[Dict] = []
        self.feedback_history: List[Dict] = []

        # Flask 兼容状态
        self._last_intent: Optional[Dict] = None
        self._last_response: Optional[Dict] = None

    async def orchestrate(self, user_intent: UserIntent) -> Dict[str, Any]:
        """
        主编排方法

        Args:
            user_intent: 用户意图 (目的地、时长、预算、偏好等)

        Returns:
            {
                "status": "success" | "error",
                "final_plan": {...},
                "ui_modules": {...},
                "quality_score": float,
                "iterations": int,
                "suggestions": [...],
                "execution_log": [...]
            }
        """
        print("\n" + "="*60)
        print("多Agent行程规划系统启动")
        print("="*60)
        print(f"目的地: {user_intent.destination}")
        print(f"时长: {user_intent.duration_days}天")
        print(f"预算: ¥{user_intent.budget}")
        print("="*60 + "\n")

        try:
            context = PlanningContext(user_intent=user_intent)

            iteration = 0
            while iteration < self.MAX_ITERATIONS:
                iteration += 1
                context.iteration_count = iteration

                print(f"\n第 {iteration} 轮迭代")
                print("-" * 60)

                if iteration == 1:
                    await self._execute_first_iteration(context)
                else:
                    await self._execute_feedback_iteration(context)

                quality_result = self._evaluate_quality(context)
                self.execution_history.append({
                    "iteration": iteration,
                    "quality_score": quality_result["overall_score"],
                    "is_acceptable": quality_result["is_acceptable"],
                    "feedback": quality_result["suggestions"]
                })

                if quality_result["is_acceptable"]:
                    print(f"\n第{iteration}轮：方案质量满足要求 (评分: {quality_result['overall_score']:.2f})")
                    context.quality_score = quality_result["overall_score"]
                    context.iteration_result = "completed"
                    break
                elif iteration >= self.MAX_ITERATIONS:
                    print(f"\n已达到最大迭代次数")
                    context.quality_score = quality_result["overall_score"]
                    context.iteration_result = "max_iterations_reached"
                    break
                else:
                    print(f"\n第{iteration}轮：需要改进 (评分: {quality_result['overall_score']:.2f})")
                    self.feedback_history.append(quality_result["feedback_per_agent"])
                    context.quality_score = quality_result["overall_score"]

            final_response = self._generate_final_response(context)

            print("\n" + "="*60)
            print("规划完成")
            print("="*60)
            print(f"总迭代数: {iteration}")
            print(f"最终评分: {context.quality_score:.2f}")
            print(f"状态: {final_response['status']}")
            print("="*60 + "\n")

            return final_response

        except Exception as e:
            print(f"\n编排过程出错: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e),
                "ui_modules": None,
                "quality_score": 0.0,
                "iterations": 0,
                "suggestions": [],
                "execution_log": self.execution_history,
            }

    def _preprocess_thematic_tags(self, context: PlanningContext) -> None:
        """
        预处理步骤（DataCollection 之前执行）：
        当用户输入包含游戏/影视/IP/非地理主题（如"仙剑奇侠传3"）时，
        调用 LLM 快速提取实地景观特征标签存入 context.thematic_tags，
        供 DataCollectionAgent 扩展高德搜索关键词。
        """
        special_req = (context.user_intent.special_requirements or "").strip()
        if not special_req or not self._llm:
            return

        # 只在 special_requirements 中含有非地理性信息时才处理
        geo_words = ["住宿", "酒店", "民宿", "交通", "预算", "自驾", "高铁", "航班"]
        if any(w in special_req for w in geo_words):
            return  # 普通需求，不需要 IP 解析

        # 如果 special_req 只是提到去某个知名景区/公园，跳过主题标签提取：
        # 该景区由 _extract_user_mentioned_pois 单独处理，
        # 若在此再提取主题标签，会让全程搜索词偏向该景区子景点，
        # 导致其他天行程也被同一主题绑定（"一天去迪士尼"≠"全程迪士尼主题"）。
        # 只有"IP/虚构世界 → 需要映射到真实地名"的情况才需要主题预处理。
        known_venues = [
            "迪士尼", "环球影城", "海昌", "欢乐谷", "长隆", "方特",
            "乐高乐园", "动物园", "水上乐园", "宋城", "横店", "华侨城",
        ]
        if any(v in special_req for v in known_venues):
            return  # 是真实景区直接访问，非虚构 IP，无需主题映射

        print(f"\n0. 主题预处理: 解析特殊需求 → '{special_req[:40]}...'")
        try:
            prompt = (
                f"用户要去{context.user_intent.destination}旅行，特殊需求/背景是：{special_req}\n"
                f"请提取4~6个能用于高德地图搜索的实地景观特征关键词（如：古镇、溶洞、悬崖、道观、山地森林）。"
                f"只输出 JSON 数组，例如：[\"古镇\", \"道观\", \"溶洞\"]"
            )
            resp = self._llm.chat(messages=[
                {"role": "system", "content": "你是旅行地理专家，只输出 JSON 数组。"},
                {"role": "user", "content": prompt},
            ])
            tags = self._llm.extract_json(resp)
            if isinstance(tags, list) and tags:
                context.thematic_tags = [str(t) for t in tags if t]
                print(f"   主题标签: {context.thematic_tags}")
        except Exception as e:
            print(f"   主题预处理失败（不影响主流程）: {e}")

    def _extract_user_mentioned_pois(self, context: PlanningContext) -> None:
        """
        Step 1.5: 从用户原始输入中提取明确点名的具体地点（敏感级最高）。
        比 _inject_narrative_anchors（AI叙事推断）优先级更高，rating=5.5。
        应在 DataCollectionAgent 之后、CultureAgent 之前执行。
        """
        # 优先用原始查询文本，其次用 special_requirements
        raw_text = (
            (context.user_intent.raw_query or "") or
            (context.user_intent.special_requirements or "")
        ).strip()
        if not raw_text or not self._amap_raw or not self._llm:
            return

        destination = _first_city(context.user_intent.destination)
        print(f"\n1.5 用户点名地点提取: 从 '{raw_text[:50]}' 提取具体地点...")

        try:
            resp = self._llm.chat(messages=[
                {"role": "system", "content": "你是地名提取专家，只输出 JSON 数组。"},
                {"role": "user", "content": (
                    f"从以下旅行需求文本中提取用户明确点名的具体地点。\n"
                    f"规则：\n"
                    f"  - 只提取用户明确说想去的真实地名或景区品牌名（如迪士尼、环球影城、故宫等均算）\n"
                    f"  - 不要包含目的地城市本身（如'{destination}'不算）\n"
                    f"  - 不要泛指描述（如'古镇'、'山景'不算，必须是具体地名）\n"
                    f"  - 每个地点标注类型: attraction/restaurant/hotel\n"
                    f"原始文本：{raw_text}\n"
                    f"目的地：{destination}\n"
                    f"只输出 JSON 数组，示例："
                    f'[{{"name": "迪士尼", "type": "attraction"}}, '
                    f'{{"name": "磁器口", "type": "attraction"}}]'
                )},
            ], max_tokens=256)
            items = self._llm.extract_json(resp)
            if not isinstance(items, list) or not items:
                print("   未识别到明确地点")
                return
        except Exception as e:
            print(f"   用户地点提取失败（非致命）: {e}")
            return

        existing_names = {p.name for p in context.pois}
        injected = []

        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            poi_type = item.get("type", "attraction")
            if len(name) < 2:
                continue

            # 检查是否已在 context.pois：直接提升评分
            matched = next(
                (ep for ep in context.pois
                 if ep.name == name or (len(name) >= 3 and name in ep.name)),
                None
            )
            if matched:
                matched.rating = 5.5
                matched.is_user_mentioned = True   # type: ignore[attr-defined]
                matched.is_narrative_anchor = True  # 复用锚点保护标记
                injected.append(f"{matched.name}(已有↑5.5)")
                continue

            # 不在已有 POI 中：Amap 精确搜索并注入
            try:
                res = self._amap_raw.search_pois(
                    keywords=name, city=destination, page_size=5
                )
                pois_raw = res.get("pois", [])
            except Exception:
                continue
            if not pois_raw:
                continue

            # 优先选景区/公园类型，过滤掉商场店铺
            # 高德 type 字段：旅游景点 > 主题公园 / 度假区 / 游乐场
            # 零售店特征：type='购物服务' 或 name 包含'(xxx店)''旗舰店''专卖店'
            _STORE_PATTERNS = re.compile(r'[\(（][^\)）]*[店铺馆][\)）]|旗舰店|专卖店|零售|商场店')
            _PARK_TYPE_WORDS = {"旅游景点", "公园", "游乐", "度假", "主题", "景区"}

            def _is_store(poi_dict: dict) -> bool:
                poi_n = poi_dict.get("name", "")
                poi_t = poi_dict.get("type", "")
                if "购物" in poi_t and not any(w in poi_t for w in _PARK_TYPE_WORDS):
                    return True
                if _STORE_PATTERNS.search(poi_n):
                    return True
                return False

            # 优先取非店铺结果；全是店铺则退回第一条
            p = next((r for r in pois_raw if not _is_store(r)), pois_raw[0])

            loc = p.get("location", "")
            if not loc or "," not in loc:
                continue
            try:
                lng_s, lat_s = loc.split(",", 1)
                lat, lng = float(lat_s), float(lng_s)
            except ValueError:
                continue

            poi_name = p.get("name", name)
            if poi_name in existing_names:
                # 已经在集合中，提升评分
                for ep in context.pois:
                    if ep.name == poi_name:
                        ep.rating = 5.5
                        ep.is_user_mentioned = True  # type: ignore[attr-defined]
                        ep.is_narrative_anchor = True  # type: ignore[attr-defined]
                        injected.append(f"{poi_name}(已有↑5.5)")
                        break
                continue

            category = (
                "餐厅" if poi_type == "restaurant" else
                ("酒店" if poi_type == "hotel" else "景点")
            )
            new_poi = POI(
                id=f"user_{len(injected)}",
                name=poi_name,
                category=category,
                location={"lat": lat, "lng": lng},
                rating=5.5,
                price=0,
            )
            new_poi.is_user_mentioned = True   # type: ignore[attr-defined]
            new_poi.is_narrative_anchor = True  # 复用锚点保护标记
            new_poi.address = p.get("address", "")  # type: ignore[attr-defined]
            context.pois.append(new_poi)
            existing_names.add(poi_name)
            injected.append(poi_name)

        if injected:
            context.user_mentioned_pois = [
                s.split("(")[0] for s in injected
            ]
            print(f"   用户点名地点: {injected}")
        else:
            print("   未识别到需强制安排的具体地点")

    def _inject_narrative_anchors(self, context: PlanningContext) -> None:
        """
        叙事锚点注入（CultureAgent 执行之后调用）：
        从 cultural_narrative 中用 LLM 提取具体地名，精确 Amap 搜索后
        注入 context.pois（rating=5.0），确保叙事提到的地方出现在行程里。
        """
        narrative = context.cultural_narrative or ""
        if not narrative or not self._amap_raw or not self._llm:
            return

        destination = _first_city(context.user_intent.destination)
        existing_names = {p.name for p in context.pois}

        # 用 LLM 精确提取地名（区分真实景点 vs 虚构/泛指描述词）
        try:
            resp = self._llm.chat(messages=[
                {"role": "system", "content": "你是地名识别专家，只输出 JSON 数组，不要解释。"},
                {"role": "user", "content": (
                    f"从以下旅行叙事中提取所有【真实可搜索】的景点地名。\n"
                    f"规则：只选现实中存在的地名；去掉游戏虚构地名（如'锁妖塔'）和泛指描述（如'古镇集市'）。\n"
                    f"目的地：{destination}\n"
                    f"叙事：{narrative}\n"
                    f"输出 JSON 字符串数组，例如：[\"磁器口古镇\", \"长江索道\", \"老君洞\"]"
                )},
            ], max_tokens=256)
            names = self._llm.extract_json(resp)
            if not isinstance(names, list) or not names:
                return
        except Exception as e:
            print(f"   叙事锚点提取失败: {e}")
            return

        injected = []

        # 收集「用户明确点名」POI 的坐标，用于拦截同园区子景点
        # 背景：用户说"有一天去迪士尼" → CultureAgent 叙事会提到 奇幻童话城堡/探险岛 等
        #       若把它们逐一注入为独立锚点，RouteAgent 会将子景点分配到不同天
        # 修复：待注入锚点与 user_mentioned POI 距离 ≤ 1km → 视为同园区 → 跳过注入
        import math as _math_mod
        user_mentioned_locs: list = [
            (p.location.get("lat", 0), p.location.get("lng", 0))
            for p in context.pois
            if getattr(p, "is_user_mentioned", False)
            and p.location.get("lat") and p.location.get("lng")
        ]

        def _near_user_mentioned(lat: float, lng: float, threshold_km: float = 1.0) -> bool:
            for ulat, ulng in user_mentioned_locs:
                R = 6371.0
                dlat = _math_mod.radians(lat - ulat)
                dlng = _math_mod.radians(lng - ulng)
                a = (_math_mod.sin(dlat/2)**2
                     + _math_mod.cos(_math_mod.radians(ulat))
                     * _math_mod.cos(_math_mod.radians(lat))
                     * _math_mod.sin(dlng/2)**2)
                if 2 * R * _math_mod.asin(_math_mod.sqrt(max(0.0, min(1.0, a)))) <= threshold_km:
                    return True
            return False

        # 用所有 POI 的坐标均值作为城市中心（比 pois[0] 更稳健）
        # pois[0] 可能是餐厅/酒店导致坐标偏移，且空列表时直接崩溃
        lats = [p.location.get("lat", 0) for p in context.pois if p.location.get("lat")]
        lngs = [p.location.get("lng", 0) for p in context.pois if p.location.get("lng")]
        city_center_lat = sum(lats) / len(lats) if lats else 0
        city_center_lng = sum(lngs) / len(lngs) if lngs else 0
        MAX_ANCHOR_KM = 80.0   # 超过80km认为无法纳入市区游程

        def _km_dist(lat1, lon1, lat2, lon2):
            """快速 Haversine 距离（km）"""
            import math
            R = 6371
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
            return R * 2 * math.asin(math.sqrt(a))

        for raw_name in names:
            name = str(raw_name).strip()
            if len(name) < 2:
                continue

            # 已存在：直接提升评分
            for ep in context.pois:
                if ep.name == name or (len(name) >= 3 and name in ep.name):
                    ep_lat = ep.location.get("lat", 0)
                    ep_lng = ep.location.get("lng", 0)
                    # 是 user_mentioned 景区的同园区子景点 → 跳过独立注入，
                    # 避免「探险岛」「奇幻城堡」等被分配到与主景区不同的天
                    if user_mentioned_locs and ep_lat and ep_lng \
                            and _near_user_mentioned(ep_lat, ep_lng):
                        break
                    if float(ep.rating or 0) < 5.0:
                        ep.rating = 5.0
                    ep.is_narrative_anchor = True  # type: ignore[attr-defined]
                    injected.append(f"{ep.name}(↑5.0)")
                    break
            else:
                # 不存在：Amap 精确搜索并注入
                try:
                    res = self._amap_raw.search_pois(keywords=name, city=destination, page_size=3)
                    pois_raw = res.get("pois", [])
                except Exception:
                    continue
                if not pois_raw:
                    continue
                p = pois_raw[0]
                loc = p.get("location", "")
                if not loc or "," not in loc:
                    continue
                try:
                    lng_s, lat_s = loc.split(",", 1)
                    lat, lng = float(lat_s), float(lng_s)
                except ValueError:
                    continue
                # 同园区子景点（在 user_mentioned 1km 内）→ 不作为独立锚点注入
                if user_mentioned_locs and _near_user_mentioned(lat, lng):
                    continue
                # 距离过滤：超过 80km 的地点跳过（如武隆/仙女山距主城>100km）
                if city_center_lat and city_center_lng:
                    dist = _km_dist(city_center_lat, city_center_lng, lat, lng)
                    if dist > MAX_ANCHOR_KM:
                        print(f"   叙事锚点跳过 '{name}'（距城市中心 {dist:.0f}km，超过 {MAX_ANCHOR_KM}km 限制）")
                        continue
                poi_name = p.get("name", name)
                if poi_name in existing_names:
                    continue
                anchor = POI(
                    id=f"anchor_{len(injected)}",
                    name=poi_name,
                    category=p.get("type", "景点"),
                    location={"lat": lat, "lng": lng},
                    rating=5.0,
                    price=0,
                )
                anchor.address = p.get("address", "")          # type: ignore[attr-defined]
                anchor.is_narrative_anchor = True               # type: ignore[attr-defined]
                context.pois.append(anchor)
                existing_names.add(poi_name)
                injected.append(poi_name)

        if injected:
            print(f"   叙事锚点注入: {injected}")

    async def _execute_first_iteration(self, context: PlanningContext) -> None:
        """第一轮迭代：主题预处理 + 数据采集 + 文化分析 + 路线优化"""

        # Step 0: 主题标签预处理（IP/游戏/影视 → 地理特征词）
        self._preprocess_thematic_tags(context)

        print("\n1. 数据采集Agent执行...")
        try:
            data_result = self.data_collection_agent.execute(context)
            context.add_agent_output(data_result)
            print(f"   POI数: {len(context.pois)}")
            print(f"   已获取天气数据")
            print(f"   基础路线: {len(context.routes)}条")
        except Exception as e:
            print(f"   数据采集失败: {e}")
            raise

        # Step 1.5: 用户明确点名的地点（DataCollection 之后提取，可检查已有 POI 并覆写）
        try:
            self._extract_user_mentioned_pois(context)
        except Exception as e:
            print(f"   用户地点提取失败（非致命）: {e}")

        print("\n2. 文化体验Agent执行...")
        try:
            culture_result = self.culture_agent.execute(context)
            context.add_agent_output(culture_result)
            print(f"   文化主题: {context.cultural_theme}")
            print(f"   文化POI: {len(context.cultural_pois)}个")
            print(f"   活动: {len(context.cultural_activities)}项")
        except Exception as e:
            print(f"   文化分析失败: {e}")
            raise

        # Step 2.5：从叙事中提取地名，确保叙事提到的景点出现在行程
        print("\n2.5 叙事锚点注入...")
        try:
            self._inject_narrative_anchors(context)
        except Exception as e:
            print(f"   锚点注入失败（非致命）: {e}")

        print("\n3. 路线优化Agent执行...")
        try:
            self._run_route_agent(context)
        except Exception as e:
            print(f"   路线优化失败(非致命): {e}")

        print("\n4. 预算规划Agent执行...")
        try:
            budget_result = self.budget_agent.execute(context)
            context.add_agent_output(budget_result)
            budget = context.budget_allocation or {}
            total = sum(budget.values()) if budget else 0
            print(f"   预算分配完成: 共¥{total:.0f} / 总预算¥{context.user_intent.budget:.0f}")
            print(f"   状态: {context.budget_status}")
        except Exception as e:
            print(f"   预算规划失败(非致命): {e}")

    # 餐厅类别关键词（与 app.py 保持一致）
    _RESTAURANT_KEYWORDS = {"餐", "饭", "美食", "小吃", "菜", "食", "火锅", "面", "粉", "restaurant", "food"}
    _HOTEL_KEYWORDS = {"酒店", "住宿", "民宿", "宾馆", "客栈", "旅馆", "旅社", "hotel", "accommodation"}

    def _is_restaurant(self, poi) -> bool:
        cat = (poi.category or "").lower()
        return any(k in cat for k in self._RESTAURANT_KEYWORDS)

    def _is_hotel(self, poi) -> bool:
        cat = (poi.category or "").lower()
        return any(k in cat for k in self._HOTEL_KEYWORDS)

    def _run_route_agent(self, context: PlanningContext) -> None:
        """调用RouteOptimizationAgent并将结果写入context
        只将景点传入路线规划，餐厅在路线确定后按就近原则添加，酒店不参与路线。
        """
        # 分离景点、餐厅、酒店
        attraction_pois = []
        restaurant_pois = []
        for poi in context.pois:
            if self._is_hotel(poi):
                continue  # 酒店完全排除在路线之外
            elif self._is_restaurant(poi):
                restaurant_pois.append(poi)
            else:
                attraction_pois.append(poi)

        # 从 CultureAgent 输出提取文化 POI 名称，用于提升路线规划中的优先级
        cultural_names: set = set()
        for cpoi in (context.cultural_pois or []):
            if isinstance(cpoi, dict):
                cultural_names.add(cpoi.get("name", ""))
            else:
                cultural_names.add(getattr(cpoi, "name", ""))
        if cultural_names:
            print(f"   文化POI加权: {len(cultural_names)}个 → 路线优先级+1.0")

        pois_for_route = []
        for poi in attraction_pois:
            base_rating = float(poi.rating or 3.0)
            is_anchor = bool(getattr(poi, "is_narrative_anchor", False))
            is_user_poi = bool(getattr(poi, "is_user_mentioned", False))
            # 优先级: 用户明确点名(5.5) > 叙事锚点(5.0) > 文化POI(+1.0)
            if is_user_poi:
                effective_rating = 5.5  # 用户明确意图，最高优先级
            elif is_anchor:
                effective_rating = 5.0
            elif poi.name in cultural_names:
                effective_rating = min(5.0, base_rating + 1.0)
            else:
                effective_rating = base_rating
            pois_for_route.append({
                "id": poi.id,
                "name": poi.name,
                "category": poi.category,
                "latitude": poi.location.get("lat", 0),
                "longitude": poi.location.get("lng", 0),
                "address": poi.address if hasattr(poi, "address") else "",
                "rating": effective_rating,
                "visit_duration": 120,
                "cost": poi.price,
                "is_anchor": is_anchor or is_user_poi,  # 用户点名也受戏截断保护
            })

        # ── 名称前缀去重：同地点多 POI 只保留评分最高一个 ──
        # 场景：高德常把"洪崖洞-大桥对面拍照打卡点"、"洪崖洞民俗风貌区"、"洪崖洞夜景观景台"
        # 作为3条独立 POI 返回，K-means 把它们分到不同天形成大量重复
        # 陷阱1："洪崖洞" 只有3字，s[:4] 取不到4字 → 与"洪崖洞民俗风貌区"的"洪崖洞民"不同
        # 陷阱2："重庆十八梯"以城市名开头 → 与"十八梯观景台"前缀不对齐
        # 修复：先剥城市名前缀，再统一取前3字作为地点指纹
        _CITY_PREFIXES_RE = re.compile(
            r'^(重庆市?|北京市?|上海市?|成都市?|西安市?|广州市?|深圳市?|'
            r'南京市?|杭州市?|武汉市?|天津市?|苏州市?|厦门市?|青岛市?)'
        )
        def _name_prefix(name: str) -> str:
            """取地点名称指纹：
            1. 去掉'-'后的副名称（高德常加拍照打卡点等描述）
            2. 去掉常见后缀
            3. 去掉城市名前缀
            4. 取前3字作为地点代表（3字足以区分不同景点，又能合并同景点变体）
            """
            s = re.sub(r'[-—·(（].*$', '', name).strip()          # 去副标题
            s = re.sub(r'(拍照打卡点|观景台|夜景|风貌区|大桥对面'
                       r'|入口处?|正门|附近|停车场|景区店|旗舰店)$', '', s).strip()
            s = _CITY_PREFIXES_RE.sub('', s).strip()               # 去城市名前缀
            return s[:3] if len(s) >= 3 else s                     # 取前3字

        seen_pfx: dict = {}          # prefix → 在 deduped_pois 中的 index
        deduped_pois: list = []
        for p in pois_for_route:
            pfx = _name_prefix(p["name"])
            if not pfx or len(pfx) < 2:      # 极短名称直接保留，不做合并
                deduped_pois.append(p)
                continue
            if pfx in seen_pfx:
                idx = seen_pfx[pfx]
                # 保留评分最高的那个
                if float(p["rating"] or 0) > float(deduped_pois[idx]["rating"] or 0):
                    deduped_pois[idx] = p
            else:
                seen_pfx[pfx] = len(deduped_pois)
                deduped_pois.append(p)
        removed_dup = len(pois_for_route) - len(deduped_pois)
        if removed_dup:
            print(f"   名称去重: {len(pois_for_route)} → {len(deduped_pois)} 个景点（合并 {removed_dup} 个重名 POI）")
        pois_for_route = deduped_pois

        # ── 主题过滤：有文化主题时，直接移除不相关的游乐场/猫猫公园 ──
        # 注意：之前只"降权"，但 RouteAgent Pass1 对 is_full_day 景点优先分配且不看评分，
        # 导致降权后的"萤火虫港湾猫猫主题公园"仍独占一天 → 改为直接从候选池删除
        thematic_tags = context.thematic_tags or []
        fun_park_kws = {"游乐", "主题公园", "动物园", "萤火虫", "猫猫", "欢乐谷",
                        "水上乐园", "嘉年华", "卡通", "方特", "宋城"}
        geo_kws = {"古镇", "寺", "道观", "洞", "峡", "山", "瀑布", "遗址", "博物馆",
                   "纪念馆", "码头", "老街", "古城", "城墙", "陵墓", "悬崖", "湿地", "湖", "森林"}
        is_niche_theme = bool(thematic_tags) and any(kw in " ".join(thematic_tags) for kw in geo_kws)
        if is_niche_theme:
            before_filter = len(pois_for_route)
            pois_for_route = [p for p in pois_for_route
                              if not any(kw in p["name"] for kw in fun_park_kws)]
            cnt_removed = before_filter - len(pois_for_route)
            if cnt_removed:
                print(f"   主题过滤: 直接移除 {cnt_removed} 个非主题游乐景点")

        # 按评分排序后限制输入量：叙事锚点强制保留，其余取高评分景点
        pois_for_route.sort(key=lambda p: -(p["rating"] or 0))
        max_input = max(12, context.user_intent.duration_days * 6)
        if len(pois_for_route) > max_input:
            anchors = [p for p in pois_for_route if p.get("is_anchor")]
            non_anchors = [p for p in pois_for_route if not p.get("is_anchor")]
            non_anchors = non_anchors[:max(0, max_input - len(anchors))]
            pois_for_route = anchors + non_anchors
            pois_for_route.sort(key=lambda p: -(p["rating"] or 0))  # 重新排序合并后列表
            print(f"   POI精简: → {len(pois_for_route)}（含锚点 {len(anchors)} 个）")

        # 餐厅数据供后续就近匹配
        restaurants_data = [
            {
                "id": poi.id,
                "name": poi.name,
                "latitude": poi.location.get("lat", 0),
                "longitude": poi.location.get("lng", 0),
                "rating": poi.rating,
                "cost": poi.price,
            }
            for poi in restaurant_pois
        ]

        if not pois_for_route:
            print("   无POI数据，跳过路线优化")
            return

        constraints = {
            "duration_days": context.user_intent.duration_days,
            "budget": context.user_intent.budget,
            "max_daily_distance": 80.0,
            "max_daily_hours": 10.0,
        }

        route_plan = self.route_agent.plan(
            pois_for_route, constraints, restaurants=restaurants_data
        )

        context.optimized_routes = route_plan.get("routes", [])
        context.final_itinerary = {
            "destination": route_plan.get("destination"),
            "duration_days": route_plan.get("duration_days"),
            "total_distance": route_plan.get("total_distance", 0),
            "total_cost": route_plan.get("total_cost", 0),
            "feasibility": route_plan.get("feasibility", True),
            "warnings": route_plan.get("warnings", []),
            "routes": route_plan.get("routes", []),
            "total_hours": sum(
                r.get("total_duration", 0) for r in route_plan.get("routes", [])
            ),
        }

        print(f"   景点: {len(attraction_pois)}个, 餐厅: {len(restaurant_pois)}个 (酒店已排除)")
        print(f"   优化路线: {len(context.optimized_routes)}天")
        print(f"   总距离: {route_plan.get('total_distance', 0):.1f}km")
        for w in route_plan.get("warnings", []):
            print(f"   警告: {w}")

    async def _execute_feedback_iteration(self, context: PlanningContext) -> None:
        """后续轮迭代：根据上一轮反馈进行调整"""
        if not self.feedback_history:
            return

        last_feedback = self.feedback_history[-1]
        agents_to_run = []

        print(f"\n反馈内容:")
        for agent_name, feedback in last_feedback.items():
            if feedback.get("status") == "feedback_needed":
                print(f"   {agent_name}: {feedback.get('issue')}")
                agents_to_run.append(agent_name)
                # 将完整反馈字典存入 context，供对应 Agent 读取细粒度指令
                context.improvement_suggestions = context.improvement_suggestions or {}
                context.improvement_suggestions[agent_name] = feedback

        if not agents_to_run:
            print("   无需改进")
            return

        print(f"\n让相关Agent进行改进...")
        for agent_name in agents_to_run:
            if agent_name == "data_collection_agent":
                print(f"   重新运行数据采集Agent（扩大搜索范围）...")
                try:
                    data_result = self.data_collection_agent.execute(context)
                    context.add_agent_output(data_result)
                    print(f"   补充后POI总数: {len(context.pois)}")
                    # 数据更新后重新执行文化分析和路线优化
                    culture_result = self.culture_agent.execute(context)
                    context.add_agent_output(culture_result)
                    self._run_route_agent(context)
                except Exception as e:
                    print(f"   数据采集重试失败: {e}")
            elif agent_name == "culture_agent":
                print(f"   重新运行文化体验Agent...")
                try:
                    culture_result = self.culture_agent.execute(context)
                    context.add_agent_output(culture_result)
                except Exception as e:
                    print(f"   文化Agent重试失败: {e}")
            elif agent_name == "route_agent":
                print(f"   重新运行路线规划Agent...")
                try:
                    self._run_route_agent(context)
                except Exception as e:
                    print(f"   路线Agent重试失败: {e}")
            elif agent_name == "budget_agent":
                print(f"   重新运行预算规划Agent...")
                try:
                    budget_result = self.budget_agent.execute(context)
                    context.add_agent_output(budget_result)
                    print(f"   预算重新分配: {context.budget_status}")
                except Exception as e:
                    print(f"   预算Agent重试失败: {e}")

    def _evaluate_quality(self, context: PlanningContext) -> Dict[str, Any]:
        """执行质量评估"""
        print("\n质量评估Agent执行...")
        try:
            quality_output = self.quality_eval_agent.execute(context)
            context.add_agent_output(quality_output)

            if quality_output.status == "error":
                print(f"   评估失败: {quality_output.error_message}")
                return {
                    "overall_score": 0.5,
                    "is_acceptable": False,
                    "suggestions": ["评估过程出错"],
                    "feedback_per_agent": {}
                }

            eval_result = quality_output.result
            print(f"   综合评分: {eval_result['overall_score']:.2f}")

            scores = eval_result.get("scores", {})
            if scores:
                print(f"   完整性: {scores.get('completeness', 0):.2f}")
                print(f"   可行性: {scores.get('feasibility', 0):.2f}")
                print(f"   用户匹配: {scores.get('user_fit', 0):.2f}")
                print(f"   体验质量: {scores.get('experience_quality', 0):.2f}")

            for i, s in enumerate(eval_result.get("suggestions", []), 1):
                print(f"   建议{i}: {s}")

            return eval_result

        except Exception as e:
            print(f"   质量评估出错: {e}")
            return {
                "overall_score": 0.5,
                "is_acceptable": False,
                "suggestions": [str(e)],
                "feedback_per_agent": {}
            }

    def _generate_final_response(self, context: PlanningContext) -> Dict[str, Any]:
        """生成最终响应：融合所有Agent输出 + UI模块"""
        print("\n生成最终响应...")
        try:
            final_plan = self._merge_agent_outputs(context)
            ui_response = UIResponseBuilder.build_full_response(context)

            print(f"   融合{len(context.agent_outputs)}个Agent输出")
            print(f"   生成{len(ui_response.get('modules', {}))}个UI模块")

            return {
                "status": "success",
                "final_plan": final_plan,
                "ui_modules": ui_response,
                "quality_score": context.quality_score,
                "iterations": context.iteration_count,
                "suggestions": self.execution_history[-1].get("feedback", []) if self.execution_history else [],
                "execution_log": self.execution_history,
            }

        except Exception as e:
            print(f"   响应生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e),
                "final_plan": None,
                "ui_modules": None,
                "quality_score": context.quality_score,
                "iterations": context.iteration_count,
            }

    def _merge_agent_outputs(self, context: PlanningContext) -> Dict[str, Any]:
        """融合所有Agent的输出成最终规划"""
        return {
            "destination": context.user_intent.destination if context.user_intent else None,
            "duration_days": context.user_intent.duration_days if context.user_intent else None,
            "created_at": datetime.now().isoformat(),
            "pois": [
                {
                    "id": p.id, "name": p.name, "category": p.category,
                    "location": p.location, "rating": p.rating, "price": p.price,
                    "opening_hours": p.opening_hours, "description": p.description,
                    "images": p.images,
                }
                for p in context.pois
            ],
            "weather": context.weather,
            "cultural_theme": context.cultural_theme,
            "cultural_narrative": context.cultural_narrative,
            "cultural_background": context.cultural_background,
            "cultural_pois": context.cultural_pois,
            "activities": context.cultural_activities,
            "experiences": context.special_experiences,
            "itinerary": context.final_itinerary,
            "optimized_routes": context.optimized_routes,
            "budget_allocation": context.budget_allocation,
            "contingency_plans": context.contingency_plans,
        }

    def save_session(self, user_id: str, session_name: str, response: Dict[str, Any]) -> str:
        """保存本次规划会话"""
        session_id = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"\n会话已保存: {session_id}")
        return session_id

    def get_execution_summary(self) -> Dict[str, Any]:
        """获取执行摘要"""
        return {
            "total_iterations": len(self.execution_history),
            "final_quality_score": self.execution_history[-1]["quality_score"] if self.execution_history else 0.0,
            "execution_history": self.execution_history,
            "feedback_history": self.feedback_history,
        }

    # ================================================================
    #  Flask 兼容接口：自然语言入口 + 同步包装
    # ================================================================

    def parse_intent(self, text: str) -> UserIntent:
        """
        将自然语言解析为结构化 UserIntent

        使用 DeepSeek LLM；无 API Key 时降级为关键词提取。
        """
        if self._llm:
            prompt = """请分析以下用户输入，提取旅行意图信息。

用户输入：{user_input}

【重要】如果用户输入明显不是旅行需求（如：数学题、打招呼、乱码、无意义文字），
请将 is_travel_request 设为 false，destination 设为 null。

【多城市处理】若用户提及多个城市（如"上海、苏州10日游"），
destination 只填写第一个/主要城市（如"上海"），
其余城市记入 special_requirements（如"同程：苏州"）。

请严格以JSON格式返回，包含以下字段（不确定的填null）：

```json
{{
    "is_travel_request": true或false,
    "destination": "目的地城市/地区",
    "departure_city": "出发城市",
    "start_date": "出发日期",
    "end_date": "返回日期",
    "duration_days": 天数(整数),
    "budget": 预算金额(数字,单位元,不确定填null),
    "travelers": 旅行人数(整数),
    "preferences": ["偏好标签列表, 如: 自然风光, 历史文化, 美食, 乡村体验, 亲子, 户外运动"],
    "accommodation_type": "住宿偏好: 豪华酒店/中档酒店/经济型/民宿/农家乐/不限",
    "transport_preference": "交通偏好: 自驾/高铁/飞机/公共交通/不限",
    "special_requirements": "其他特殊需求(字符串)"
}}
```

【preferences 填写规则】
- 只根据用户明确表达的偏好填写，不要从景点/活动名称反向推断
- 例如：用户提到迪士尼/环球影城/游乐园，不代表"亲子"（除非用户说了"带孩子"/"亲子游"）
- 用户没有表达偏好时，preferences 填 []""".replace("{user_input}", text)

            try:
                response = self._llm.chat(
                    messages=[
                        {"role": "system", "content": "你是旅行意图分析专家。请严格返回JSON格式。"},
                        {"role": "user", "content": prompt},
                    ]
                )
                intent_dict = self._llm.extract_json(response)
                if intent_dict:
                    # 检测非旅行请求
                    if intent_dict.get("is_travel_request") is False:
                        raise ValueError("输入内容不是旅行规划需求，请输入目的地或旅行描述（例如：上海3日游）")
                    if intent_dict.get("destination"):
                        parsed_days = int(intent_dict.get("duration_days") or 3)
                        # 未指定预算时按天数估算：¥800/天（含住宿、餐饮、门票）
                        estimated_budget = parsed_days * 800
                        raw_dest = intent_dict["destination"]
                        # 防御：即使 LLM 忽略多城市指令，也强制取第一个城市
                        primary_dest = _first_city(raw_dest)
                        if primary_dest != raw_dest:
                            print(f"[parse_intent] 多城市目的地 '{raw_dest}' → 主目的地 '{primary_dest}'")
                        return UserIntent(
                            destination=primary_dest,
                            start_date=intent_dict.get("start_date"),
                            end_date=intent_dict.get("end_date"),
                            duration_days=parsed_days,
                            budget=float(intent_dict.get("budget") or estimated_budget),
                            people_count=int(intent_dict.get("travelers") or 1),
                            preferences=intent_dict.get("preferences") or [],
                            accommodation_type=intent_dict.get("accommodation_type"),
                            transport_preference=intent_dict.get("transport_preference"),
                            special_requirements=intent_dict.get("special_requirements"),
                        )
            except ValueError:
                raise  # 非旅行请求直接向上抛出
            except Exception as e:
                print(f"[parse_intent] LLM 解析失败，降级处理: {e}")

        # 降级：简单关键词提取（仅在 LLM 不可用时使用）
        import re
        # 基本合法性检查：拒绝明显非目的地的输入
        travel_keywords = [
            '旅游', '旅行', '出行', '游玩', '游览', '观光', '度假', '自驾',
            '酒店', '住宿', '景点', '路线', '哪里', '去哪', '推荐',
        ]
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in text)
        has_travel_keyword = any(kw in text for kw in travel_keywords)
        # 若字符串全是数字/符号/英文且无旅行关键词，拒绝
        if not has_chinese and not has_travel_keyword:
            raise ValueError("无法识别旅行目的地，请输入目的地或旅行描述（例如：上海3日游）")

        days_match = re.search(r'(\d+)\s*[天日]', text)
        budget_match = re.search(r'(\d+)\s*元|预算\s*(\d+)', text)
        duration = int(days_match.group(1)) if days_match else 3
        budget = float(budget_match.group(1) or budget_match.group(2)) if budget_match else duration * 800
        # 从文本中提取目的地：去除前缀词后取第一个城市
        destination_text = re.sub(r'^(我想|想要|想去|帮我|请帮|规划|一个?)\s*', '', text)
        # 截取城市部分：取第一批汉字（遇到数字、日、天、游等截断）
        city_match = re.match(r'([\u4e00-\u9fff、，,/+&]+)', destination_text)
        raw_city = city_match.group(1).rstrip('的去想') if city_match else destination_text[:10]
        primary_dest = _first_city(raw_city)
        if primary_dest != raw_city:
            print(f"[parse_intent:fallback] 多城市 '{raw_city}' → '{primary_dest}'")
        return UserIntent(destination=primary_dest, duration_days=duration, budget=budget)

    def plan_sync(self, query: str) -> Dict[str, Any]:
        """
        同步入口：自然语言 → 完整规划（供 Flask 调用）

        返回与 orchestrate() 相同的 response dict，
        同时将 last_intent / last_response 存储到实例属性。

        Raises:
            ValueError: 输入为空或无法识别为旅行需求时
        """
        query = (query or "").strip()
        if len(query) < 2:
            raise ValueError("请输入旅行目的地或需求描述（例如：上海3日游）")

        print(f"\n[plan_sync] 解析意图: {query[:60]}...")
        user_intent = self.parse_intent(query)
        # 将原始查询文本存入 UserIntent，供 _extract_user_mentioned_pois 使用
        user_intent.raw_query = query
        print(f"[plan_sync] 目的地={user_intent.destination}, "
              f"天数={user_intent.duration_days}, 预算={user_intent.budget}")

        self._last_intent = {
            "destination": user_intent.destination,
            "duration_days": user_intent.duration_days,
            "budget": user_intent.budget,
            "preferences": user_intent.preferences,
            "start_date": user_intent.start_date,
            "end_date": user_intent.end_date,
            "accommodation_type": user_intent.accommodation_type,
            "transport_preference": user_intent.transport_preference,
            "special_requirements": user_intent.special_requirements,
            "notice": None,
        }

        # 检测多城市输入 → 给前端提示
        # 只用 LLM 已解析的 destination 来判断，避免把句子里的逗号误判为城市分隔符
        # （如"上海三日游，有一天想去迪士尼"不应触发多城市提示）
        raw_dest = user_intent.destination or ""
        if _CITY_SEP.search(raw_dest):
            all_cities = [p.strip() for p in _CITY_SEP.split(raw_dest) if p.strip()]
            if len(all_cities) > 1:
                others = " / ".join(all_cities[1:])
                self._last_intent["notice"] = (
                    f"检测到多城市行程（{'、'.join(all_cities)}），本次将为您规划"
                    f" {all_cities[0]}。"
                    f"其他城市（{others}）可单独输入规划。"
                )

        # 重置迭代历史（每次 plan_sync 是独立请求）
        self.execution_history = []
        self.feedback_history = []

        response = asyncio.run(self.orchestrate(user_intent))
        self._last_response = response
        return response

    def build_plan_text(self, response: Dict[str, Any]) -> str:
        """从 Multi-agent 响应生成 Markdown 格式的规划文本（供前端侧边栏显示）"""
        fp = response.get("final_plan") or {}
        if not fp:
            return "规划生成失败，请重试。"

        lines = []
        dest = fp.get("destination", "目的地")
        days = fp.get("duration_days", 3)
        score = response.get("quality_score", 0)
        iters = response.get("iterations", 0)
        lines.append(f"# 🗺️ {dest} {days}天旅行规划\n")

        # 天气
        weather = fp.get("weather") or {}
        if weather.get("weather"):
            lines.append("## 🌤️ 天气提醒")
            lines.append(f"- 天气: {weather['weather']}")
            if weather.get("high_temp"):
                lines.append(f"- 气温: {weather.get('low_temp', '')}~{weather.get('high_temp', '')}℃")
            lines.append("")

        # 文化主题（narrative 优先，兜底展示 theme 名称）
        theme = fp.get("cultural_theme")
        narrative = fp.get("cultural_narrative")
        if theme or narrative:
            lines.append(f"## 🎭 文化主题")
            if theme:
                lines.append(f"**✦ {theme}**\n")
            if narrative:
                lines.append(narrative)
            lines.append("")

        # 每日路线
        routes = fp.get("optimized_routes") or []
        if routes:
            lines.append("## 📅 每日行程\n")
            for i, day in enumerate(routes, 1):
                lines.append(f"**第 {i} 天**")
                for poi in day.get("pois", []):
                    name = poi.get("name", str(poi)) if isinstance(poi, dict) else str(poi)
                    lines.append(f"- {name}")
                lines.append("")
        else:
            pois = fp.get("pois") or []
            if pois:
                lines.append("## 📍 推荐景点\n")
                for poi in pois[:12]:
                    name = poi.get("name", "")
                    cat = poi.get("category", "")
                    rating = poi.get("rating", "")
                    line = f"- **{name}** ({cat})"
                    if rating:
                        line += f" ⭐{rating}"
                    lines.append(line)
                lines.append("")

        # 特色活动
        activities = fp.get("activities") or []
        if activities:
            lines.append("## 🎯 特色活动\n")
            for act in activities[:5]:
                label = act.get("activity", str(act)) if isinstance(act, dict) else str(act)
                lines.append(f"- {label}")
            lines.append("")

        # 预算
        budget = fp.get("budget_allocation") or {}
        if budget:
            lines.append("## 💰 预算估算\n")
            total = 0.0
            for k, v in budget.items():
                try:
                    v_num = float(v)
                    lines.append(f"- {k}: ¥{v_num:.0f}")
                    total += v_num
                except (TypeError, ValueError):
                    lines.append(f"- {k}: {v}")
            if total:
                lines.append(f"- **合计: ¥{total:.0f}**")
            lines.append("")

        lines.append("---")
        lines.append(f"*方案质量: {score:.2f}/1.0 · 优化轮数: {iters}*")
        return "\n".join(lines)

    @property
    def last_intent(self) -> Optional[Dict]:
        """最近一次解析的意图（dict 格式，供 Flask 使用）"""
        return self._last_intent

    @property
    def last_response(self) -> Optional[Dict]:
        """最近一次规划响应"""
        return self._last_response


async def run_example():
    """使用示例"""
    orchestrator = TravelPlanningOrchestrator()
    user_intent = UserIntent(
        destination="安庆",
        duration_days=3,
        budget=5000,
        preferences=["文化遗产", "美食", "天然景观"]
    )
    response = await orchestrator.orchestrate(user_intent)
    print("\n最终结果:")
    print(json.dumps({
        "status": response["status"],
        "quality_score": response["quality_score"],
        "iterations": response["iterations"],
        "destination": response.get("final_plan", {}).get("destination") if response.get("final_plan") else None,
    }, indent=2, ensure_ascii=False))
    if response["status"] == "success":
        orchestrator.save_session("user_123", "安庆三日游", response)
    return response


if __name__ == "__main__":
    result = asyncio.run(run_example())
