"""
前端UI模块化展示配置
定义各个模块的数据结构和展示规则
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Union
from enum import Enum


class ModuleType(Enum):
    """模块类型"""
    ITINERARY = "itinerary"      # 行程规划
    CULTURE = "culture"           # 文化体验
    BUDGET = "budget"            # 预算规划
    NAVIGATION = "navigation"    # 导航地图
    KNOWLEDGE = "knowledge"      # 知识库
    EXECUTION = "execution"      # 执行详情
    CONTINGENCY = "contingency"  # 应急预案


@dataclass
class ItineraryModule:
    """行程规划模块数据"""
    days: int
    schedule: List[Dict[str, Any]]  # 每天的日程
    tips: List[str]
    packing_list: List[str]
    contact_info: Dict[str, str]


@dataclass
class CultureModule:
    """文化体验模块数据"""
    theme: str
    background: str
    sites: List[Dict[str, Any]]  # 文化景点
    activities: List[Dict[str, Any]]  # 推荐活动
    media: List[Dict[str, Any]]  # 图片/视频资源
    stories: List[str]


@dataclass
class BudgetModule:
    """预算规划模块数据"""
    total_budget: float
    people_count: int
    allocated: Dict[str, float]  # 各类别预算
    breakdown: List[Dict[str, Any]]  # 详细成本
    status: str  # "正常" / "超预算" / "充足"
    recommendations: List[str]


@dataclass
class NavigationModule:
    """导航地图模块数据"""
    map_center: Dict[str, float]  # {"lat": ..., "lng": ...}
    pois: List[Dict[str, Any]]  # POI点
    routes: List[Dict[str, Any]]  # 路线
    distance_km: float
    estimated_time_hours: float


@dataclass
class KnowledgeModule:
    """知识库模块数据"""
    recent_learnings: List[Dict[str, Any]]
    categories: Dict[str, int]  # 分类统计
    top_tags: List[str]
    search_enabled: bool = True


@dataclass
class ExecutionModule:
    """Agent执行详情模块数据"""
    iteration: int
    max_iterations: int
    agents_status: List[Dict[str, Any]]
    quality_score: float
    execution_log: List[str]
    current_agent: Optional[str]


@dataclass
class ContingencyModule:
    """应急预案模块数据"""
    scenarios: List[Dict[str, Any]]  # 风险场景
    alternatives: List[Dict[str, Any]]  # 备选方案
    emergency_contacts: Dict[str, str]


class UIModuleFactory:
    """UI模块工厂 - 从Agent输出转换为UI模块"""
    
    @staticmethod
    def create_itinerary_module(agent_output: Dict[str, Any]) -> ItineraryModule:
        """创建行程规划模块"""
        return ItineraryModule(
            days=agent_output.get("days", 0),
            schedule=agent_output.get("itinerary", []),
            tips=agent_output.get("travel_tips", []),
            packing_list=agent_output.get("packing_list", []),
            contact_info=agent_output.get("contacts", {})
        )
    
    @staticmethod
    def create_culture_module(agent_output: Dict[str, Any]) -> CultureModule:
        """创建文化体验模块"""
        return CultureModule(
            theme=agent_output.get("cultural_theme", ""),
            background=agent_output.get("background_story", ""),
            sites=agent_output.get("cultural_pois", []),
            activities=agent_output.get("activities", []),
            media=agent_output.get("media_resources", []),
            stories=agent_output.get("cultural_stories", [])
        )
    
    @staticmethod
    def create_budget_module(agent_output: Dict[str, Any]) -> BudgetModule:
        """创建预算规划模块"""
        return BudgetModule(
            total_budget=agent_output.get("total_budget", 0),
            people_count=agent_output.get("people_count", 1),
            allocated=agent_output.get("budget_allocation", {}),
            breakdown=agent_output.get("cost_details", []),
            status=agent_output.get("budget_status", "未知"),
            recommendations=agent_output.get("recommendations", [])
        )
    
    @staticmethod
    def create_navigation_module(agent_output: Dict[str, Any]) -> NavigationModule:
        """创建导航地图模块"""
        return NavigationModule(
            map_center=agent_output.get("map_center", {"lat": 30.5, "lng": 117.0}),
            pois=agent_output.get("pois", []),
            routes=agent_output.get("routes", []),
            distance_km=agent_output.get("total_distance_km", 0),
            estimated_time_hours=agent_output.get("total_time_hours", 0)
        )
    
    @staticmethod
    def create_knowledge_module(kb_stats: Dict[str, Any]) -> KnowledgeModule:
        """创建知识库模块"""
        return KnowledgeModule(
            recent_learnings=kb_stats.get("recent_knowledge", []),
            categories=kb_stats.get("by_category", {}),
            top_tags=kb_stats.get("top_tags", []),
            search_enabled=True
        )
    
    @staticmethod
    def create_execution_module(context: Any) -> ExecutionModule:
        """创建Agent执行详情模块"""
        return ExecutionModule(
            iteration=context.iteration_count,
            max_iterations=5,
            agents_status=[
                {
                    "name": output.agent_name,
                    "status": output.status,
                    "confidence": output.confidence_score
                }
                for output in context.agent_outputs[-6:]  # 最后6个输出
            ],
            quality_score=context.quality_score,
            execution_log=context.execution_log[-10:],  # 最后10条日志
            current_agent=None
        )
    
    @staticmethod
    def create_contingency_module(agent_output: Dict[str, Any]) -> ContingencyModule:
        """创建应急预案模块"""
        return ContingencyModule(
            scenarios=agent_output.get("contingency_plans", []),
            alternatives=agent_output.get("alternatives", []),
            emergency_contacts=agent_output.get("emergency_contacts", {})
        )


class UIResponseBuilder:
    """UI响应构建器 - 组织模块数据用于前端展示"""
    
    @staticmethod
    def build_full_response(context: Any, kb_manager: Any) -> Dict[str, Any]:
        """
        构建完整的UI响应
        
        返回结构:
        {
            "status": "success",
            "session_id": "xxx",
            "modules": {
                "itinerary": {...},
                "culture": {...},
                "budget": {...},
                "navigation": {...},
                "knowledge": {...},
                "execution": {...},
                "contingency": {...}
            },
            "recommendations": [...]
        }
        """
        response = {
            "status": "success",
            "session_id": context.session_id,
            "timestamp": context.updated_at,
            "quality_score": context.quality_score,
            "iteration": context.iteration_count,
            "modules": {}
        }
        
        # 构建各模块
        try:
            # 获取最新的Agent输出
            operation_output = context.get_agent_output("operation_agent")
            culture_output = context.get_agent_output("culture_agent")
            budget_output = context.get_agent_output("budget_agent")
            route_output = context.get_agent_output("route_agent")
            
            # 创建各模块
            if operation_output:
                response["modules"]["itinerary"] = UIModuleFactory.create_itinerary_module(
                    operation_output.result
                ).__dict__
            
            if culture_output:
                response["modules"]["culture"] = UIModuleFactory.create_culture_module(
                    culture_output.result
                ).__dict__
            
            if budget_output:
                response["modules"]["budget"] = UIModuleFactory.create_budget_module(
                    budget_output.result
                ).__dict__
            
            if route_output:
                response["modules"]["navigation"] = UIModuleFactory.create_navigation_module(
                    route_output.result
                ).__dict__
            
            # 知识库模块
            kb_stats = kb_manager.get_kb_statistics() if kb_manager else {}
            response["modules"]["knowledge"] = UIModuleFactory.create_knowledge_module(
                kb_stats
            ).__dict__
            
            # 执行详情模块
            response["modules"]["execution"] = UIModuleFactory.create_execution_module(
                context
            ).__dict__
            
            # 应急预案模块
            if operation_output:
                response["modules"]["contingency"] = UIModuleFactory.create_contingency_module(
                    operation_output.result
                ).__dict__
        
        except Exception as e:
            print(f"构建UI模块出错: {e}")
        
        return response
    
    @staticmethod
    def build_error_response(error: str, session_id: str) -> Dict[str, Any]:
        """构建错误响应"""
        return {
            "status": "error",
            "session_id": session_id,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }


# 用于前端展示的JSON Schema示例
FRONTEND_SCHEMA = {
    "itinerary": {
        "type": "object",
        "properties": {
            "days": {"type": "integer"},
            "schedule": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "time": {"type": "string"},
                        "activity": {"type": "string"},
                        "duration_minutes": {"type": "integer"},
                        "location": {"type": "string"},
                        "tips": {"type": "string"}
                    }
                }
            }
        }
    },
    "culture": {
        "type": "object",
        "properties": {
            "theme": {"type": "string"},
            "sites": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "story": {"type": "string"},
                        "images": {"type": "array", "items": {"type": "string"}},
                        "activity": {"type": "string"}
                    }
                }
            }
        }
    }
}


from datetime import datetime
