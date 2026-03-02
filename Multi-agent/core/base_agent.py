"""
旅游规划Agent基类 - 基于LangChain框架
实现了Agent的基本生命周期和通信机制
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable
import json
from datetime import datetime

from .planning_context import PlanningContext, AgentOutput
from .agent_state import AgentStateMachine, AgentState
from .agent_memory import AgentMemory


class TravelPlanningAgent(ABC):
    """旅游规划Agent基类"""
    
    def __init__(self, name: str, llm=None, tools: List = None):
        """
        初始化Agent
        
        Args:
            name: Agent名称
            llm: 语言模型(DeepSeek等)
            tools: LangChain工具列表
        """
        self.name = name
        self.llm = llm
        self.tools = tools or []
        
        # 状态机
        self.state_machine = AgentStateMachine(name)
        
        # 内存管理
        self.memory = AgentMemory(name)
        
        # 执行统计
        self.execution_count = 0
        self.success_count = 0
        self.error_count = 0
        self.current_iteration = 0
        
        # 回调函数注册
        self._register_state_callbacks()
    
    def execute(self, context: PlanningContext) -> AgentOutput:
        """
        执行Agent的主业务逻辑
        
        Args:
            context: 共享的规划上下文
            
        Returns:
            Agent的输出结果
        """
        self.current_iteration = context.iteration_count
        self.execution_count += 1
        
        # Step 1: 验证输入
        if not self._validate_input(context):
            return self._create_error_output("输入验证失败")
        
        # Step 2: 状态转换 - IDLE → PREPARING
        self.state_machine.transition(AgentState.PREPARING, trigger="execute")
        
        try:
            # Step 3: 状态转换 - PREPARING → EXECUTING
            self.state_machine.transition(AgentState.EXECUTING, trigger="start_execution")
            
            # Step 4: 执行核心逻辑
            result = self._execute_core(context)
            
            # Step 5: 处理反馈
            unprocessed_feedback = self.memory.get_unprocessed_feedback()
            if unprocessed_feedback:
                result = self._process_feedback(result, unprocessed_feedback, context)
            
            # Step 6: 状态转换 - EXECUTING → SUCCESS
            self.state_machine.transition(AgentState.SUCCESS, trigger="execution_success")
            self.success_count += 1
            
            # Step 7: 创建输出
            output = AgentOutput(
                agent_name=self.name,
                iteration=self.current_iteration,
                status="success",
                result=result,
                confidence_score=self._calculate_confidence(result, context)
            )
            
            # Step 8: 保存执行记录
            self.memory.add_execution_record(self.current_iteration, result)
            
            return output
            
        except Exception as e:
            self.error_count += 1
            self.state_machine.transition(AgentState.ERROR, trigger="execution_error")
            self.memory.add_error(str(e), {"traceback": str(e)}, self.current_iteration)
            return self._create_error_output(str(e))
    
    def receive_feedback(self, feedback: Dict[str, Any], from_agent: str):
        """
        接收来自其他Agent的反馈
        
        Args:
            feedback: 反馈内容
            from_agent: 反馈来源Agent
        """
        self.memory.add_feedback(feedback, from_agent, self.current_iteration)
        
        # 如果当前在执行中，可以进行调整
        if self.state_machine.current_state == AgentState.EXECUTING:
            self.state_machine.transition(AgentState.FEEDBACK, trigger="feedback_received")
    
    def learn_and_store(self, learning: Dict[str, Any]):
        """
        学习新知识并存储到知识库
        
        Args:
            learning: 学习的新知识
        """
        self.memory.add_learning(learning, self.current_iteration)
    
    @abstractmethod
    def _execute_core(self, context: PlanningContext) -> Dict[str, Any]:
        """
        执行核心业务逻辑 - 子类实现
        
        Args:
            context: 规划上下文
            
        Returns:
            执行结果
        """
        pass
    
    @abstractmethod
    def _validate_input(self, context: PlanningContext) -> bool:
        """验证输入数据是否充分"""
        pass
    
    def _process_feedback(self, result: Dict[str, Any],
                         feedback_list: List[Dict[str, Any]],
                         context: PlanningContext) -> Dict[str, Any]:
        """
        处理反馈并调整结果
        默认实现：将反馈建议合并到结果中
        子类可以覆盖此方法进行自定义反馈处理
        """
        for feedback in feedback_list:
            if "suggestions" in feedback:
                result.setdefault("adjustments", []).append({
                    "from": feedback.get("from_agent", "unknown"),
                    "suggestion": feedback["suggestions"]
                })
            # 标记为已处理
            feedback["processed"] = True

        return result
    
    def _calculate_confidence(self, result: Dict[str, Any], 
                            context: PlanningContext) -> float:
        """
        计算结果的置信度
        范围: 0.0 - 1.0
        """
        confidence = 0.8
        
        # 如果有错误记录，降低置信度
        if "errors" in result or "warnings" in result:
            confidence -= 0.2
        
        # 如果通过了多次验证，提高置信度
        if "validation_passed" in result:
            confidence += 0.1
        
        return min(1.0, max(0.0, confidence))
    
    def _create_error_output(self, error_msg: str) -> AgentOutput:
        """创建错误输出"""
        return AgentOutput(
            agent_name=self.name,
            iteration=self.current_iteration,
            status="error",
            error_message=error_msg,
            confidence_score=0.0
        )
    
    def _register_state_callbacks(self):
        """注册状态转换回调"""
        self.state_machine.register_callback(
            AgentState.EXECUTING,
            lambda: print(f"[{self.name}] 开始执行...")
        )
        self.state_machine.register_callback(
            AgentState.SUCCESS,
            lambda: print(f"[{self.name}] ✓ 执行成功")
        )
        self.state_machine.register_callback(
            AgentState.ERROR,
            lambda: print(f"[{self.name}] ✗ 执行出错")
        )
    
    def get_status(self) -> Dict[str, Any]:
        """获取Agent的当前状态"""
        return {
            "name": self.name,
            "state": self.state_machine.current_state.value,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": self.success_count / max(1, self.execution_count),
            "memory_summary": self.memory.get_memory_summary()
        }
    
    def reset(self):
        """重置Agent状态"""
        self.state_machine.reset()
        self.memory.clear()
        self.execution_count = 0
        self.success_count = 0
        self.error_count = 0
    
    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name} state={self.state_machine.current_state.value}>"
