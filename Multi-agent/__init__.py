"""
多Agent行程规划系统
===================

核心模块:
- core: 核心框架 (PlanningContext, Agent状态机, 内存系统)
- agents: 具体Agent实现 (数据采集、文化分析、质量评估)
- knowledge_base: 知识库系统 (自动学习、持久化)
- orchestrator: 编排器 (Agent协调、迭代反馈)
- api: REST API接口
- ui_modules: 前端UI模块
"""

from multi_agent_orchestrator import TravelPlanningOrchestrator
from core.planning_context import PlanningContext, UserIntent, AgentOutput
from core.base_agent import TravelPlanningAgent
from agents.data_collection_agent import DataCollectionAgent
from agents.culture_agent import CultureAgent
from agents.quality_eval_agent import QualityEvalAgent

__version__ = "1.0.0"
__all__ = [
    "TravelPlanningOrchestrator",
    "PlanningContext",
    "UserIntent",
    "AgentOutput",
    "TravelPlanningAgent",
    "DataCollectionAgent",
    "CultureAgent",
    "QualityEvalAgent"
]
