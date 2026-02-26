"""
预算规划Agent - 估算旅行总费用并按类别分配预算
"""

import math
from typing import Dict, Any

from core.base_agent import TravelPlanningAgent
from core.planning_context import PlanningContext


class BudgetAgent(TravelPlanningAgent):
    """
    预算规划Agent

    职责：
      1. 汇总景点门票费用（来自 POI.price）
      2. 按住宿偏好估算住宿费
      3. 按交通偏好估算交通费
      4. 按天数估算餐饮和杂费
      5. 将分配结果写入 context.budget_allocation / context.budget_status
    """

    # 住宿类型 → 每晚均价（元/间）
    _ACCOMMODATION_COST: Dict[str, float] = {
        "豪华酒店": 900, "五星酒店": 900, "四星酒店": 550,
        "中档酒店": 350, "三星酒店": 350,
        "经济型": 180, "青年旅舍": 120,
        "民宿": 260, "客栈": 220, "农家乐": 140,
    }
    _DEFAULT_ACCOMMODATION: float = 300  # 未指定时每晚默认值（元）

    # 交通偏好 → 每天均价（元/人）
    _TRANSPORT_COST: Dict[str, float] = {
        "自驾": 130, "租车": 130,
        "高铁": 90, "动车": 80, "火车": 60,
        "飞机": 200,
        "公共交通": 30, "地铁": 25,
        "出租车": 110, "滴滴": 100,
    }
    _DEFAULT_TRANSPORT: float = 65   # 未指定时每天默认值（元）

    _MEAL_PER_DAY: float = 160       # 餐饮估算（元/人/天，含早中晚）
    _MISC_PER_DAY: float = 80        # 杂费（购物、娱乐、小费等）

    def __init__(self):
        super().__init__(name="budget_agent")

    def _validate_input(self, context: PlanningContext) -> bool:
        if not context.user_intent:
            self.memory.add_error("缺少用户意图", {}, self.current_iteration)
            return False
        return True

    def _execute_core(self, context: PlanningContext) -> Dict[str, Any]:
        """
        核心业务逻辑

        读取 context.pois / user_intent，计算预算分配写入 context。
        """
        intent = context.user_intent
        days = max(1, int(intent.duration_days or 3))
        total_budget = float(intent.budget or days * 800)
        people = max(1, int(intent.people_count or 1))

        # ── 1. 景点门票（仅统计最终行程中景点的门票，而不是全部 381 个候选 POI）
        # 旧逻辑：遍历 context.pois 全集 → 会把所有候选POI的price加总，导致虚假超预算
        # 修复：先从 final_itinerary.routes 取出行程内的POI名称，只统计这些POI的ticket
        itinerary_names: set = set()
        if context.final_itinerary:
            for day_route in context.final_itinerary.get("routes", []):
                for p in day_route.get("pois", []):
                    n = p.get("name", "")
                    if n:
                        itinerary_names.add(n)

        # 建立 name → price 映射（context.pois 是带 price 的完整 POI 对象）
        poi_price_map: Dict[str, float] = {}
        for poi in context.pois:
            cat = (poi.category or "").lower()
            if "餐" in cat or "hotel" in cat or "酒店" in cat or "住宿" in cat:
                continue
            if poi.price and poi.price > 0:
                poi_price_map[poi.name] = float(poi.price)

        attraction_cost = 0.0
        if itinerary_names:
            # 优先：只统计行程内的景点
            for name in itinerary_names:
                attraction_cost += poi_price_map.get(name, 0.0)
        else:
            # 降级：行程未生成时（极少发生），用所有候选景点 price 均值 × 天数 × 3
            # 避免全量加总导致虚假超预算
            prices = list(poi_price_map.values())
            if prices:
                avg_price = sum(prices) / len(prices)
                attraction_cost = round(avg_price * days * 3, 0)  # 每天约3个付费景点
        attraction_cost = round(attraction_cost, 0)

        # ── 2. 住宿（按天数-1晚，以免计算出发/返回日）
        nights = max(0, days - 1)
        accom_type = (intent.accommodation_type or "").strip()
        nightly_rate = self._DEFAULT_ACCOMMODATION
        for key, rate in self._ACCOMMODATION_COST.items():
            if key in accom_type:
                nightly_rate = rate
                break
        accommodation_cost = round(nightly_rate * nights * people, 0)

        # ── 3. 交通
        transport_pref = (intent.transport_preference or "").strip()
        daily_transport = self._DEFAULT_TRANSPORT
        for key, rate in self._TRANSPORT_COST.items():
            if key in transport_pref:
                daily_transport = rate
                break
        transport_cost = round(daily_transport * days * people, 0)

        # ── 4. 餐饮 & 杂费
        meal_cost = round(self._MEAL_PER_DAY * days * people, 0)
        misc_cost = round(self._MISC_PER_DAY * days * people, 0)

        budget_allocation = {
            "景点门票": attraction_cost,
            "住宿":     accommodation_cost,
            "交通":     transport_cost,
            "餐饮":     meal_cost,
            "杂费":     misc_cost,
        }

        total_estimated = sum(budget_allocation.values())
        over_budget = total_estimated > total_budget
        over_amount = max(0.0, total_estimated - total_budget)
        savings = max(0.0, total_budget - total_estimated)

        # 写回 context
        context.budget_allocation = budget_allocation
        context.budget_status = "超预算" if over_budget else "在预算内"

        print(f"   预算分配: 门票{attraction_cost:.0f} + 住宿{accommodation_cost:.0f}"
              f" + 交通{transport_cost:.0f} + 餐饮{meal_cost:.0f} + 杂费{misc_cost:.0f}"
              f" = ¥{total_estimated:.0f} / ¥{total_budget:.0f} ({context.budget_status})")
        if over_budget:
            print(f"   超预算: ¥{over_amount:.0f}")
        else:
            print(f"   剩余预算: ¥{savings:.0f}")

        return {
            "budget_allocation": budget_allocation,
            "total_estimated": total_estimated,
            "total_budget": total_budget,
            "over_budget": over_budget,
            "budget_status": context.budget_status,
            "over_amount": over_amount,
            "savings": savings,
            "per_day": round(total_estimated / days, 0),
            "per_person": round(total_estimated / people, 0),
        }
