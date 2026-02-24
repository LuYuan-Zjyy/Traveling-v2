"""
规划上下文 - 多Agent共享的数据结构
所有Agent通过这个上下文共享信息和更新状态
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional
from datetime import datetime
import json


@dataclass
class UserIntent:
    """用户旅行意图"""
    destination: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_days: int = 3
    budget: float = 5000
    people_count: int = 1
    preferences: List[str] = field(default_factory=list)
    accommodation_type: Optional[str] = None
    transport_preference: Optional[str] = None
    special_requirements: Optional[str] = None


@dataclass
class POI:
    """兴趣点"""
    id: str
    name: str
    category: str  # attraction, restaurant, hotel, etc.
    location: Dict[str, float]  # {"lat": ..., "lng": ...}
    rating: Optional[float] = None
    price: Optional[float] = None
    opening_hours: Optional[str] = None
    description: Optional[str] = None
    images: List[str] = field(default_factory=list)


@dataclass
class AgentOutput:
    """Agent输出结果"""
    agent_name: str
    iteration: int
    status: str  # success, error, feedback_needed
    result: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    confidence_score: float = 1.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class PlanningContext:
    """
    多Agent共享的规划上下文
    用于存储整个规划过程中的所有数据
    """
    
    def __init__(self):
        # Step 0: 用户意图
        self.user_intent: Optional[UserIntent] = None
        
        # Step 1: 原始数据
        self.pois: List[POI] = []
        self.weather: Optional[Dict[str, Any]] = None
        self.routes: List[Dict[str, Any]] = []
        self.external_data: Dict[str, Any] = {}
        
        # Step 2: 文化处理
        self.cultural_theme: Optional[str] = None
        self.cultural_pois: List[POI] = []
        self.cultural_activities: List[Dict[str, Any]] = []
        self.cultural_background: Dict[str, str] = {}  # {poi_id: story}
        
        # Step 3: 路由优化
        self.optimized_routes: List[Dict[str, Any]] = []
        self.selected_route: Optional[Dict[str, Any]] = None
        
        # Step 4: 费用规划
        self.budget_allocation: Optional[Dict[str, float]] = None
        self.cost_details: List[Dict[str, Any]] = []
        self.budget_status: Optional[str] = None
        
        # Step 5: 运营优化
        self.final_itinerary: Optional[Dict[str, Any]] = None
        self.contingency_plans: List[Dict[str, Any]] = []
        self.rest_recommendations: List[Dict[str, Any]] = []
        
        # Agent执行历史
        self.agent_outputs: List[AgentOutput] = []
        self.execution_log: List[str] = []
        
        # 元数据
        self.created_at: str = datetime.now().isoformat()
        self.updated_at: str = datetime.now().isoformat()
        self.session_id: str = self._generate_session_id()
        self.quality_score: float = 0.0
        self.iteration_count: int = 0
    
    def add_agent_output(self, output: AgentOutput):
        """添加Agent输出到上下文"""
        self.agent_outputs.append(output)
        self.updated_at = datetime.now().isoformat()
        self.execution_log.append(
            f"[{output.timestamp}] {output.agent_name}: {output.status} "
            f"(confidence: {output.confidence_score:.2f})"
        )
    
    def get_agent_output(self, agent_name: str, iteration: Optional[int] = None) -> Optional[AgentOutput]:
        """获取特定Agent的最新输出"""
        outputs = [o for o in self.agent_outputs if o.agent_name == agent_name]
        if iteration is not None:
            outputs = [o for o in outputs if o.iteration == iteration]
        return outputs[-1] if outputs else None
    
    def increment_iteration(self):
        """增加迭代计数"""
        self.iteration_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_intent": asdict(self.user_intent) if self.user_intent else None,
            "cultural_theme": self.cultural_theme,
            "optimized_routes": self.optimized_routes,
            "budget_allocation": self.budget_allocation,
            "final_itinerary": self.final_itinerary,
            "contingency_plans": self.contingency_plans,
            "quality_score": self.quality_score,
            "iteration_count": self.iteration_count,
            "session_id": self.session_id
        }
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @staticmethod
    def _generate_session_id() -> str:
        """生成会话ID"""
        from uuid import uuid4
        return str(uuid4())[:8]
    
    def __repr__(self):
        return f"<PlanningContext session_id={self.session_id} iteration={self.iteration_count}>"
