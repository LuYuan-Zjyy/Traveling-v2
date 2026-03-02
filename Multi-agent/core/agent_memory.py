"""
Agent内存管理 - 存储Agent的执行历史、反馈、学习内容
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import deque


@dataclass
class Memory:
    """内存项"""
    type: str  # "execution", "feedback", "learning", "error"
    content: Dict[str, Any]
    timestamp: str
    iteration: int
    importance_score: float = 0.5


class AgentMemory:
    """Agent内存管理 (类似Long-term和Short-term Memory)"""
    
    def __init__(self, agent_name: str, short_term_capacity: int = 20):
        self.agent_name = agent_name
        self.short_term_capacity = short_term_capacity
        
        # 短期记忆 (最近的操作和反馈)
        self.short_term_memory: deque = deque(maxlen=short_term_capacity)
        
        # 长期记忆 (重要的发现和模式)
        self.long_term_memory: List[Memory] = []
        
        # 反馈历史
        self.feedback_history: List[Dict[str, Any]] = []
        
        # 错误历史
        self.error_history: List[Dict[str, Any]] = []
    
    def add_execution_record(self, iteration: int, result: Dict[str, Any]):
        """添加执行记录"""
        memory = Memory(
            type="execution",
            content=result,
            timestamp=datetime.now().isoformat(),
            iteration=iteration,
            importance_score=0.3
        )
        self.short_term_memory.append(memory)
    
    def add_feedback(self, feedback: Dict[str, Any], sender_agent: str, iteration: int):
        """接收来自其他Agent的反馈"""
        feedback_item = {
            "timestamp": datetime.now().isoformat(),
            "from_agent": sender_agent,
            "iteration": iteration,
            "content": feedback,
            "processed": False
        }
        self.feedback_history.append(feedback_item)
        
        # 同时添加到短期记忆
        memory = Memory(
            type="feedback",
            content={"sender": sender_agent, "feedback": feedback},
            timestamp=datetime.now().isoformat(),
            iteration=iteration,
            importance_score=0.8  # 反馈很重要
        )
        self.short_term_memory.append(memory)
    
    def add_learning(self, learning: Dict[str, Any], iteration: int):
        """增加学习记录 (用于知识库)"""
        memory = Memory(
            type="learning",
            content=learning,
            timestamp=datetime.now().isoformat(),
            iteration=iteration,
            importance_score=0.9
        )
        self.long_term_memory.append(memory)
    
    def add_error(self, error: str, details: Dict[str, Any], iteration: int):
        """记录错误"""
        error_item = {
            "timestamp": datetime.now().isoformat(),
            "iteration": iteration,
            "error": error,
            "details": details
        }
        self.error_history.append(error_item)
    
    def get_unprocessed_feedback(self) -> List[Dict[str, Any]]:
        """获取待处理的反馈"""
        return [f for f in self.feedback_history if not f["processed"]]
    
    def mark_feedback_processed(self, feedback_index: int):
        """标记反馈为已处理"""
        if 0 <= feedback_index < len(self.feedback_history):
            self.feedback_history[feedback_index]["processed"] = True
    
    def get_recent_memories(self, count: int = 5, memory_type: Optional[str] = None) -> List[Memory]:
        """获取最近的内存"""
        memories = list(self.short_term_memory)
        if memory_type:
            memories = [m for m in memories if m.type == memory_type]
        return memories[-count:]
    
    def get_important_learnings(self, min_score: float = 0.7) -> List[Memory]:
        """获取重要的学习记录"""
        return [m for m in self.long_term_memory if m.importance_score >= min_score]
    
    def get_error_patterns(self) -> Dict[str, int]:
        """分析错误模式"""
        error_patterns = {}
        for error_item in self.error_history:
            error = error_item["error"]
            error_patterns[error] = error_patterns.get(error, 0) + 1
        return error_patterns
    
    def get_memory_summary(self) -> Dict[str, Any]:
        """获取内存摘要"""
        return {
            "short_term_size": len(self.short_term_memory),
            "long_term_size": len(self.long_term_memory),
            "unprocessed_feedback_count": len(self.get_unprocessed_feedback()),
            "error_count": len(self.error_history),
            "recent_errors": [e["error"] for e in self.error_history[-3:]],
            "error_patterns": self.get_error_patterns()
        }
    
    def clear(self):
        """清空所有内存"""
        self.short_term_memory.clear()
        self.long_term_memory.clear()
        self.feedback_history.clear()
        self.error_history.clear()
    
    def __repr__(self):
        return f"<AgentMemory agent={self.agent_name} " \
               f"short_term={len(self.short_term_memory)} " \
               f"long_term={len(self.long_term_memory)}>"
