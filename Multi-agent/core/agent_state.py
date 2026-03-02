"""
Agent状态机 - 管理Agent的生命周期状态
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any
from datetime import datetime


class AgentState(Enum):
    """Agent状态枚举"""
    IDLE = "idle"              # 空闲
    PREPARING = "preparing"    # 准备
    EXECUTING = "executing"    # 执行中
    SUCCESS = "success"        # 成功
    FEEDBACK = "feedback"      # 需要反馈
    ERROR = "error"            # 错误
    COMPLETED = "completed"    # 完成


@dataclass
class StateTransition:
    """状态转换"""
    from_state: AgentState
    to_state: AgentState
    trigger: str
    timestamp: str
    metadata: Dict[str, Any]


class AgentStateMachine:
    """Agent状态机"""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.current_state = AgentState.IDLE
        self.state_history: list[StateTransition] = []
        self.state_callbacks: Dict[AgentState, Callable] = {}
    
    def transition(self, new_state: AgentState, trigger: str = "", 
                   metadata: Dict[str, Any] = None):
        """状态转换"""
        if new_state == self.current_state:
            return
        
        transition = StateTransition(
            from_state=self.current_state,
            to_state=new_state,
            trigger=trigger,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {}
        )
        
        self.state_history.append(transition)
        old_state = self.current_state
        self.current_state = new_state
        
        # 触发回调
        if new_state in self.state_callbacks:
            self.state_callbacks[new_state]()
    
    def register_callback(self, state: AgentState, callback: Callable):
        """注册状态转换回调"""
        self.state_callbacks[state] = callback
    
    def can_transition_to(self, new_state: AgentState) -> bool:
        """检查是否可以转换到新状态"""
        # 定义合法的状态转换
        valid_transitions = {
            AgentState.IDLE: [AgentState.PREPARING],
            AgentState.PREPARING: [AgentState.EXECUTING, AgentState.ERROR],
            AgentState.EXECUTING: [AgentState.SUCCESS, AgentState.FEEDBACK, AgentState.ERROR],
            AgentState.SUCCESS: [AgentState.COMPLETED],
            AgentState.FEEDBACK: [AgentState.EXECUTING],  # 接收反馈后重新执行
            AgentState.ERROR: [AgentState.PREPARING],
            AgentState.COMPLETED: [AgentState.IDLE],  # 可以重新开始
        }
        
        return new_state in valid_transitions.get(self.current_state, [])
    
    def get_state_history(self) -> list[StateTransition]:
        """获取完整的状态历史"""
        return self.state_history
    
    def is_terminal_state(self) -> bool:
        """是否处于终端状态"""
        return self.current_state in [AgentState.COMPLETED, AgentState.ERROR]
    
    def reset(self):
        """重置状态机"""
        self.current_state = AgentState.IDLE
        self.state_history.clear()
    
    def __repr__(self):
        return f"<AgentStateMachine agent={self.agent_name} state={self.current_state.value}>"
