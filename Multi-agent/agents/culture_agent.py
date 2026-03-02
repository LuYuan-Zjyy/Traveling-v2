"""
文化体验Agent v2 - 用 LLM + 搜索引擎彻底打破主题枷锁
职责：主题识别、POI 二次筛选打分、生成叙事型行程介绍
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from core.base_agent import TravelPlanningAgent
from core.planning_context import PlanningContext, POI


class CultureAgent(TravelPlanningAgent):
    """
    文化体验 Agent【核心差异化 Agent】

    v2 改造要点：
    ① LLM 优先：不再依赖硬编码 cultural_db，任何输入（包括"仙剑奇侠传3"）
       均由 DeepSeek 解析出：
         - theme_name（精炼主题名）
         - geographic_tags（实地景观特征标签，用于 POI 打分）
         - narrative（叙事介绍段落，直接填充前端"文化主题"栏）
    ② 搜索引擎增强：用搜索结果中的网友推荐景点与高德 POI 做交叉比对，
       被网友提及的景点额外加权。
    ③ 兜底安全网：LLM / 网络均不可用时，退化为轻量关键词规则，
       保证系统始终可运行。
    """

    def __init__(self, llm_client=None, search_tool=None):
        super().__init__(name="culture_agent")
        self.llm_client = llm_client
        self.search_tool = search_tool
        self._fallback_db = self._init_fallback_db()

    # ─────────────────────────────────────────────
    #  主执行逻辑
    # ─────────────────────────────────────────────

    def _validate_input(self, context: PlanningContext) -> bool:
        if not context.user_intent:
            self.memory.add_error("缺少用户意图", {}, self.current_iteration)
            return False
        return True

    def _execute_core(self, context: PlanningContext) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "cultural_theme": "",
            "cultural_narrative": "",
            "cultural_pois": [],
            "cultural_background": {},
            "activities": [],
            "special_experiences": [],
            "status": "success",
        }

        destination = context.user_intent.destination
        preferences = context.user_intent.preferences or []
        special_req = context.user_intent.special_requirements or ""
        preset_tags = list(context.thematic_tags) if context.thematic_tags else []

        # Step 1: 主题分析（LLM 或兜底）
        theme_info = self._analyze_theme(destination, preferences, special_req, preset_tags)
        theme_name: str = theme_info["theme_name"]
        geo_tags: List[str] = theme_info["geographic_tags"]
        narrative: str = theme_info["narrative"]

        result["cultural_theme"] = theme_name
        result["cultural_narrative"] = narrative
        context.cultural_theme = theme_name
        context.cultural_narrative = narrative
        print(f"✓ 文化主题: {theme_name}")
        print(f"✓ 地理标签: {geo_tags}")

        # Step 2: 搜索引擎增强（可选）
        search_recommended: List[str] = []
        if self.search_tool:
            try:
                sr = self.search_tool.search_travel_theme(destination, theme_name, max_results=6)
                search_recommended = self.search_tool.extract_poi_names_from_results(sr, destination)
                if search_recommended:
                    print(f"✓ 搜索引擎推荐景点: {search_recommended[:5]}")
            except Exception as e:
                print(f"  搜索引擎增强失败（不影响主流程）: {e}")

        # Step 3: POI 二次打分
        if context.pois:
            scored_pois = self._score_pois(context.pois, geo_tags, search_recommended)
            result["cultural_pois"] = scored_pois
            context.cultural_pois = scored_pois
            print(f"✓ POI 二次打分 Top5: {[p['name'] for p in scored_pois[:5]]}")
            top_names = {p["name"] for p in scored_pois[:5]}
            for poi in context.pois:
                if poi.name in top_names:
                    result["cultural_background"][poi.id] = self._gen_poi_background(poi, theme_name, destination)
            context.cultural_background = result["cultural_background"]
            print(f"✓ 生成景点背景: {len(result['cultural_background'])} 条")

        # Step 4: 活动与体验
        activities = self._recommend_activities(destination, theme_name, preferences, geo_tags)
        result["activities"] = activities
        context.cultural_activities = activities
        experiences = self._design_experiences(destination, theme_name, geo_tags)
        result["special_experiences"] = experiences
        context.special_experiences = experiences

        self.learn_and_store({
            "type": "culture_analysis",
            "destination": destination,
            "theme": theme_name,
            "geo_tags": geo_tags,
        })
        return result

    # ─────────────────────────────────────────────
    #  主题分析
    # ─────────────────────────────────────────────

    def _analyze_theme(self, destination, preferences, special_req, preset_tags):
        if self.llm_client:
            try:
                return self._llm_analyze_theme(destination, preferences, special_req, preset_tags)
            except Exception as e:
                print(f"  [CultureAgent] LLM 分析失败，降级: {e}")
        return self._rule_analyze_theme(destination, preferences, special_req, preset_tags)

    def _llm_analyze_theme(self, destination, preferences, special_req, preset_tags):
        pref_str = "、".join(preferences) if preferences else "无"
        preset_str = "、".join(preset_tags) if preset_tags else "无"
        # 判断用户是否明确表示亲子出行，避免仅凭"迪士尼"等词就贴亲子标签
        explicit_family = any(
            w in (special_req or "") for w in
            ["亲子", "带孩子", "小孩", "儿童", "宝宝", "孩子", "family", "kid"]
        )
        family_hint = (
            "用户明确表示是亲子出行，可适当融入亲子相关视角。"
            if explicit_family else
            "注意：用户未提到带孩子/亲子游，不要因为出现迪士尼、乐园等词就自动推断为亲子主题；"
            "请从目的地文化特色与用户偏好出发规划主题。"
        )
        prompt = f"""你是一名资深旅行策划师，请根据以下信息为用户的 {destination} 旅行规划文化主题。

目的地：{destination}
用户偏好标签：{pref_str}
特殊需求/背景：{special_req if special_req else "无"}
已提取主题标签（参考）：{preset_str}
{family_hint}

请以 JSON 格式返回（只输出 JSON，不要任何额外文字）：
{{
  "theme_name": "精炼主题名，2~12字，有创意（如'仙剑3·重庆仙侠幻境七日游'而非'历史文化探索'）",
  "geographic_tags": ["与主题匹配的实地景观特征，5~8个，如'古镇老街'、'悬崖峭壁'、'道观寺庙'，用于后续景点筛选打分"],
  "narrative": "180~250字行程主题介绍：①主题来源与亮点 ②{destination}几个最符合该主题的真实地点（直接点名） ③对旅行体验的期待。语气有代入感。"
}}"""
        resp = self.llm_client.chat(messages=[
            {"role": "system", "content": "你是旅行规划主题分析专家，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ])
        parsed = self.llm_client.extract_json(resp)
        if parsed and parsed.get("theme_name"):
            return {
                "theme_name": parsed["theme_name"],
                "geographic_tags": parsed.get("geographic_tags") or [],
                "narrative": parsed.get("narrative") or "",
            }
        raise ValueError("LLM 返回无效")

    def _rule_analyze_theme(self, destination, preferences, special_req, preset_tags):
        db = self._fallback_db.get(destination, {})
        pref_map = db.get("pref_theme_map", {})
        themes = db.get("cultural_themes", [])
        tags = db.get("default_geo_tags", [])
        theme_parts = [pref_map[p] for p in preferences if p in pref_map]
        if not theme_parts and themes:
            theme_parts = themes[:2]
        if not theme_parts:
            fb = {"历史文化": "历史文化探索", "美食": "美食文化之旅", "自然风光": "自然风光游览", "亲子": "亲子探索之旅"}
            theme_parts = [fb[p] for p in preferences if p in fb]
        theme_name = " · ".join(t for t in theme_parts if t)[:20] or f"{destination}深度游"
        geo_tags = tags or preset_tags or ["景区", "古迹", "公园"]
        narrative = (
            f"本次{destination}之旅以「{theme_name}」为主题，精选最具代表性的景点，"
            f"带您深入感受当地的历史底蕴与文化风情。行程兼顾文化探索与休闲体验，"
            f"期待它成为一段难忘的旅行记忆。"
        )
        return {"theme_name": theme_name, "geographic_tags": geo_tags, "narrative": narrative}

    # ─────────────────────────────────────────────
    #  POI 二次打分
    # ─────────────────────────────────────────────

    def _score_pois(self, pois, geo_tags, search_names):
        search_set = set(search_names)
        scored = []
        for poi in pois:
            if poi.category not in ("景点", "attraction", "公园", "寺庙", "博物馆"):
                continue
            base = float(poi.rating or 3.5)
            tag_hits = sum(1 for t in geo_tags if t in f"{poi.name} {poi.description or ''}")
            search_bonus = 0.8 if any(s in poi.name or poi.name in s for s in search_set) else 0.0
            score = base + tag_hits * 0.3 + search_bonus
            scored.append({
                "poi_id": poi.id, "name": poi.name,
                "score": round(score, 2), "tag_hits": tag_hits,
                "search_recommended": search_bonus > 0,
                "rating": poi.rating, "price": poi.price,
                "reason": f"主题标签命中 {tag_hits} 个" + ("；搜索引擎推荐" if search_bonus > 0 else ""),
            })
        scored.sort(key=lambda x: -x["score"])
        return scored

    # ─────────────────────────────────────────────
    #  景点背景
    # ─────────────────────────────────────────────

    def _gen_poi_background(self, poi, theme, destination):
        if self.llm_client:
            try:
                prompt = (
                    f"请为「{destination}」景点「{poi.name}」写一段80字以内的文化背景说明，"
                    f"体现它与「{theme}」主题的关联。只输出说明文字。"
                )
                resp = self.llm_client.chat(messages=[
                    {"role": "system", "content": "你是旅行文案专家，文字简洁有感染力。"},
                    {"role": "user", "content": prompt},
                ])
                return resp.strip()[:300]
            except Exception:
                pass
        return poi.description or f"{poi.name}是{destination}的著名景点。"

    # ─────────────────────────────────────────────
    #  活动 & 体验
    # ─────────────────────────────────────────────

    def _recommend_activities(self, destination, theme, preferences, geo_tags):
        if self.llm_client:
            try:
                pref_str = "、".join(preferences) if preferences else "无"
                prompt = (
                    f"为「{destination}」的「{theme}」主题旅行推荐 3~4 个特色活动。\n"
                    f"用户偏好：{pref_str}；主题地理特征：{'、'.join(geo_tags[:4])}。\n"
                    f"以 JSON 数组返回，字段：activity（名称）、description（30字说明）、"
                    f"duration_hours（时长）、cost（估价/元）。只输出 JSON 数组。"
                )
                resp = self.llm_client.chat(messages=[
                    {"role": "system", "content": "你是旅行活动设计师，只输出 JSON 数组。"},
                    {"role": "user", "content": prompt},
                ])
                arr = self.llm_client.extract_json(resp)
                if isinstance(arr, list) and arr:
                    return arr[:5]
            except Exception as e:
                print(f"  活动推荐 LLM 失败: {e}")

        base = [
            {"activity": f"{destination}主题深度探访", "description": "跟随专业导游深入了解本地文化",
             "duration_hours": 3.0, "cost": 200},
            {"activity": "特色美食体验", "description": "品尝本地招牌菜与隐藏小吃",
             "duration_hours": 1.5, "cost": 100},
        ]
        tag_str = " ".join(geo_tags)
        if "洞" in tag_str or "峡" in tag_str:
            base.append({"activity": "溶洞/峡谷探险", "description": "体验震撼的自然奇观",
                         "duration_hours": 2.5, "cost": 150})
        if "寺" in tag_str or "道观" in tag_str:
            base.append({"activity": "禅意文化体验", "description": "参访寺庙道观",
                         "duration_hours": 1.5, "cost": 0})
        return base

    def _design_experiences(self, destination, theme, geo_tags):
        return [{
            "name": f"{theme}·主题精华一日游",
            "description": f"以「{theme}」为主线游览{destination}最具代表性的景点，深度沉浸",
            "duration_hours": 8, "cost_estimate": 500,
            "highlights": geo_tags[:3],
        }]

    # ─────────────────────────────────────────────
    #  兜底数据库
    # ─────────────────────────────────────────────

    def _init_fallback_db(self):
        return {
            "安庆": {"cultural_themes": ["黄梅戏", "乡村体验", "江南文化"],
                    "pref_theme_map": {"历史文化": "黄梅戏文化", "乡村体验": "江南乡村"},
                    "default_geo_tags": ["戏台", "古镇", "湖泊"]},
            "北京": {"cultural_themes": ["皇家文化", "胡同文化", "红色文化"],
                    "pref_theme_map": {"历史文化": "皇家文化", "美食": "胡同文化"},
                    "default_geo_tags": ["宫殿", "胡同", "四合院", "古迹"]},
            "成都": {"cultural_themes": ["巴蜀文化", "熊猫文化", "川菜文化"],
                    "pref_theme_map": {"美食": "川菜文化", "亲子": "熊猫文化"},
                    "default_geo_tags": ["古镇", "茶馆", "街巷"]},
            "重庆": {"cultural_themes": ["山城文化", "码头文化", "抗战文化", "巴渝民俗"],
                    "pref_theme_map": {"历史文化": "山城码头文化", "美食": "火锅文化",
                                       "自然风光": "山城峡谷地貌"},
                    "default_geo_tags": ["悬崖", "古镇", "码头", "山地", "溶洞"]},
            "西安": {"cultural_themes": ["秦汉文化", "丝绸之路", "古城文化"],
                    "pref_theme_map": {"历史文化": "秦汉文化", "美食": "关中民俗"},
                    "default_geo_tags": ["古城墙", "陵墓", "寺塔", "遗址"]},
            "上海": {"cultural_themes": ["海派文化", "现代都市", "工业遗存"],
                    "pref_theme_map": {"历史文化": "海派文化", "亲子": "现代都市"},
                    "default_geo_tags": ["外滩", "石库门", "弄堂", "租界"]},
            "杭州": {"cultural_themes": ["西湖文化", "江南园林", "丝绸文化"],
                    "pref_theme_map": {"自然风光": "西湖文化", "历史文化": "南宋历史"},
                    "default_geo_tags": ["湖泊", "园林", "寺庙", "茶园"]},
        }
