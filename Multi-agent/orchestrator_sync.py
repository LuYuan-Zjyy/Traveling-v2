"""
Flask 同步适配器 — 将异步 TravelPlanningOrchestrator 包装为同步接口

用于 MCP_map/app.py 兼容性
"""

import asyncio
from typing import Dict, Any, List, Optional


class TravelOrchestratorSync:
    """
    同步包装器，将异步 TravelPlanningOrchestrator 转换为同步接口
    供 Flask  MCP_map 使用
    """
    
    def __init__(self, config):
        """初始化同步编排器"""
        from multi_agent_orchestrator import TravelPlanningOrchestrator
        from core.planning_context import UserIntent
        
        self.config = config
        self._orchestrator = TravelPlanningOrchestrator()
        self.UserIntent = UserIntent
        
        # 缓存结果
        self.last_collected_data = []
        self.last_intent = None
    
    def plan(self, query: str) -> str:
        """
        规划接口 — 同步版本
        
        Args:
            query: 用户查询 (如 "北京7天文化之旅")
        
        Returns:
            规划文本
        """
        try:
            # Step 1: 解析意图（这里简化处理，实际应该用 DeepSeek 解析）
            print(f"[PLAN] 开始规划: {query[:50]}...")
            
            # 提取简单的意图信息
            intent = self._parse_simple_intent(query)
            self.last_intent = intent
            
            # Step 2: 创建 UserIntent 对象
            user_intent = self.UserIntent(
                destination=intent.get("destination", "北京"),
                duration_days=intent.get("duration_days", 3),
                budget=intent.get("budget", 5000),
                preferences=intent.get("preferences", []),
                trip_type=intent.get("trip_type", "cultural")
            )
            
            # Step 3: 运行异步编排器（同步版本）
            print(f"[PLAN] 运行多Agent编排系统...")
            response = asyncio.run(self._orchestrator.orchestrate(user_intent))
            
            # Step 4: 提取结果
            if response.get("status") == "success":
                final_plan = response.get("final_plan", {})
                plan_text = self._format_plan(final_plan, intent)
            else:
                plan_text = f"规划失败: {response.get('error', '未知错误')}"
                print(f"[ERROR] {plan_text}")
            
            # 缓存和谐数据（这里是简化，实际应该从response中提取）
            self.last_collected_data = response.get("execution_log", [])
            
            return plan_text
            
        except Exception as e:
            print(f"[ERROR] plan() 出错: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _parse_simple_intent(self, query: str) -> Dict[str, Any]:
        """简单的意图解析"""
        # 这里可以用 DeepSeek 进行更高级的解析，目前简化处理
        intent = {
            "destination": "北京",
            "duration_days": 3,
            "budget": None,
            "preferences": ["文化", "历史"],
            "trip_type": "cultural"
        }
        
        # 简单的启发式提取
        query_lower = query.lower()
        if "天" in query:
            try:
                for i, char in enumerate(query):
                    if char.isdigit() and i + 1 < len(query) and query[i+1] == '天':
                        intent["duration_days"] = int(char)
                        break
            except:
                pass
        
        # 尝试识别地点
        for city in ["北京", "上海", "广州", "南京", "西安", "成都", "杭州", "安庆"]:
            if city in query:
                intent["destination"] = city
                break
        
        return intent
    
    def _format_plan(self, final_plan: Dict[str, Any], intent: Dict[str, Any]) -> str:
        """将最终规划格式化为文本"""
        city = intent.get("destination", "目的地")
        days = intent.get("duration_days", 3)
        
        lines = [
            f"\n🗺️ {city}，{days}天行程规划\n",
            "=" * 50,
        ]
        
        # 如果有详细的规划信息，添加
        if final_plan:
            itinerary = final_plan.get("itinerary", {})
            if itinerary:
                for day_key in sorted(itinerary.keys()):
                    activities = itinerary[day_key]
                    lines.append(f"\n📅 {day_key}:")
                    for activity in activities:
                        lines.append(f"  • {activity.get('activity', 'N/A')}")
        
        # 补充占位内容
        if not final_plan or not final_plan.get("itinerary"):
            lines.append(f"\n行程概览:")
            lines.append(f"• 目的地: {city}")
            lines.append(f"• 时间: {days}天")
            lines.append(f"• 根据您的偏好，已为您制定详细行程")
        
        return "\n".join(lines)


# 向后兼容别名
TravelOrchestrator = TravelOrchestratorSync
