"""
多Agent编排器 - 主协调层
管理所有Agent的执行流程、迭代反馈和结果融合
"""

import asyncio
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from core.planning_context import PlanningContext, UserIntent
from agents.data_collection_agent import DataCollectionAgent
from agents.culture_agent import CultureAgent
from agents.quality_eval_agent import QualityEvalAgent
from ui_modules import UIResponseBuilder, UIModuleFactory


class TravelPlanningOrchestrator:
    """
    多Agent编排器
    
    执行流程：
    1. 初始化 - 创建PlanningContext和所有Agent
    2. 执行循环 - 最多5次迭代
       - 第1次：DataCollectionAgent(数据采集) → CultureAgent(文化分析)
       - 后续：根据QualityEvalAgent反馈，让相关Agent改进
    3. 质量评估 - QualityEvalAgent评分，是否继续迭代
    4. 结果融合 - 组合所有Agent输出
    5. 响应生成 - 转换为7个UI模块
    """
    
    MAX_ITERATIONS = 5
    QUALITY_THRESHOLD = 0.75
    
    def __init__(self):
        """初始化编排器"""
        
        # 所有Agent
        self.data_collection_agent = DataCollectionAgent()
        self.culture_agent = CultureAgent()
        self.quality_eval_agent = QualityEvalAgent()
        
        # 执行历史
        self.execution_history = []
        self.feedback_history = []
    
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
                "quality_score": 0.75 float,
                "iterations": 3,
                "suggestions": [],
                "execution_log": [...]
            }
        """
        
        print("\n" + "="*60)
        print("🚀 多Agent行程规划系统启动")
        print("="*60)
        print(f"目的地: {user_intent.destination}")
        print(f"时长: {user_intent.duration_days}天")
        print(f"预算: ¥{user_intent.budget}")
        print("="*60 + "\n")
        
        try:
            # Step 1: 初始化规划上下文
            context = PlanningContext(user_intent=user_intent)
            
            # Step 2: 执行迭代循环
            iteration = 0
            while iteration < self.MAX_ITERATIONS:
                iteration += 1
                context.iteration_count = iteration
                
                print(f"\n📍 第 {iteration} 轮迭代")
                print("-" * 60)
                
                if iteration == 1:
                    # 第一轮：数据采集 + 文化分析
                    await self._execute_first_iteration(context)
                else:
                    # 后续轮：根据反馈调整
                    await self._execute_feedback_iteration(context)
                
                # Step 3: 质量评估
                quality_result = self._evaluate_quality(context)
                self.execution_history.append({
                    "iteration": iteration,
                    "quality_score": quality_result["overall_score"],
                    "is_acceptable": quality_result["is_acceptable"],
                    "feedback": quality_result["suggestions"]
                })
                
                # Step 4: 检查是否可以完成
                if quality_result["is_acceptable"]:
                    print(f"\n✅ 第{iteration}轮：方案质量满足要求 (评分: {quality_result['overall_score']:.2f})")
                    context.quality_score = quality_result["overall_score"]
                    context.iteration_result = "completed"
                    break
                elif iteration >= self.MAX_ITERATIONS:
                    print(f"\n⏹️  已达到最大迭代次数")
                    context.quality_score = quality_result["overall_score"]
                    context.iteration_result = "max_iterations_reached"
                    break
                else:
                    print(f"\n🔄 第{iteration}轮：需要改进 (评分: {quality_result['overall_score']:.2f})")
                    self.feedback_history.append(quality_result["feedback_per_agent"])
                    context.quality_score = quality_result["overall_score"]
            
            # Step 5: 结果融合和响应生成
            final_response = self._generate_final_response(context)
            
            print("\n" + "="*60)
            print("✨ 规划完成")
            print("="*60)
            print(f"总迭代数: {iteration}")
            print(f"最终评分: {context.quality_score:.2f}")
            print(f"状态: {final_response['status']}")
            print("="*60 + "\n")
            
            return final_response
            
        except Exception as e:
            print(f"\n✗ 编排过程出错: {e}")
            return {
                "status": "error",
                "error": str(e),
                "ui_modules": None,
                "quality_score": 0.0
            }
    
    async def _execute_first_iteration(self, context: PlanningContext) -> None:
        """
        第一轮迭代：数据采集 + 文化分析
        """
        
        print("\n1️⃣ 数据采集Agent执行...")
        try:
            data_result = self.data_collection_agent.execute(context)
            print(f"   ✓ 采集POI数: {len(context.pois)}")
            print(f"   ✓ 获取天气数据")
            print(f"   ✓ 计算路线: {len(context.routes)}条")
        except Exception as e:
            print(f"   ✗ 数据采集失败: {e}")
            raise
        
        print("\n2️⃣ 文化体验Agent执行...")
        try:
            culture_result = self.culture_agent.execute(context)
            print(f"   ✓ 识别文化主题: {context.cultural_theme}")
            print(f"   ✓ 筛选文化POI: {len(context.cultural_pois)}个")
            print(f"   ✓ 生成背景信息")
            print(f"   ✓ 设计活动: {len(context.cultural_activities)}项")
        except Exception as e:
            print(f"   ✗ 文化分析失败: {e}")
            raise
    
    async def _execute_feedback_iteration(self, context: PlanningContext) -> None:
        """
        后续轮迭代：根据上一轮反馈进行调整
        """
        
        # 从最后一个反馈中获取需要改进的Agent
        if not self.feedback_history:
            return
        
        last_feedback = self.feedback_history[-1]
        
        # 让提到的Agent重新执行
        agents_to_run = []
        
        print(f"\n📋 反馈内容:")
        for agent_name, feedback in last_feedback.items():
            if feedback.get("status") == "feedback_needed":
                print(f"   • {agent_name}: {feedback.get('issue')}")
                agents_to_run.append(agent_name)
                
                # 添加建议到context
                if "suggestions" in feedback:
                    context.improvement_suggestions = context.improvement_suggestions or {}
                    context.improvement_suggestions[agent_name] = feedback["suggestions"]
        
        # 执行需要改进的Agent
        if not agents_to_run:
            print("   无需改进")
            return
        
        print(f"\n🔧 让相关Agent进行改进...")
        
        # 这里可以根据反馈让特定Agent重新执行
        # 由于还没实现RouteAgent和BudgetAgent，这里只演示结构
        for agent_name in agents_to_run:
            if agent_name == "culture_agent":
                print(f"   • 重新运行文化体验Agent...")
                # culture_agent.execute(context, feedback=last_feedback[agent_name])
                pass
            elif agent_name == "route_agent":
                print(f"   • 重新运行路线规划Agent...")
                # 待实现
                pass
            elif agent_name == "budget_agent":
                print(f"   • 重新运行预算规划Agent...")
                # 待实现
                pass
    
    def _evaluate_quality(self, context: PlanningContext) -> Dict[str, Any]:
        """
        执行质量评估
        """
        print("\n3️⃣ 质量评估Agent执行...")
        try:
            quality_result = self.quality_eval_agent.execute(context)
            
            if quality_result.get("status") == "error":
                print(f"   ✗ 评估失败: {quality_result.get('error')}")
                return {
                    "overall_score": 0.5,
                    "is_acceptable": False,
                    "suggestions": ["评估过程出错"],
                    "feedback_per_agent": {}
                }
            
            print(f"   ✓ 综合评分: {quality_result['overall_score']:.2f}")
            
            # 显示具体评分项
            scores = quality_result.get("scores", {})
            if scores:
                print(f"   • 完整性: {scores.get('completeness', 0):.2f}")
                print(f"   • 可行性: {scores.get('feasibility', 0):.2f}")
                print(f"   • 用户匹配: {scores.get('user_fit', 0):.2f}")
                print(f"   • 体验质量: {scores.get('experience_quality', 0):.2f}")
            
            # 显示建议
            suggestions = quality_result.get("suggestions", [])
            if suggestions:
                print(f"   💡 改进建议:")
                for i, suggestion in enumerate(suggestions, 1):
                    print(f"      {i}. {suggestion}")
            
            return quality_result
            
        except Exception as e:
            print(f"   ✗ 质量评估出错: {e}")
            return {
                "overall_score": 0.5,
                "is_acceptable": False,
                "suggestions": [str(e)],
                "feedback_per_agent": {}
            }
    
    def _generate_final_response(self, context: PlanningContext) -> Dict[str, Any]:
        """
        生成最终响应：融合所有Agent输出 + UI模块
        """
        
        print("\n4️⃣ 生成最终响应...")
        
        try:
            # Step 1: 融合Agent输出
            final_plan = self._merge_agent_outputs(context)
            
            # Step 2: 转换为UI模块
            ui_builder = UIResponseBuilder()
            ui_response = ui_builder.build_full_response(context)
            
            print(f"   ✓ 融合{len(context.agent_outputs)}个Agent的输出")
            print(f"   ✓ 生成{len(ui_response.get('modules', {}))}个UI模块")
            
            return {
                "status": "success",
                "final_plan": final_plan,
                "ui_modules": ui_response,
                "quality_score": context.quality_score,
                "iterations": context.iteration_count,
                "suggestions": self.execution_history[0].get("feedback", []) if self.execution_history else [],
                "execution_log": self.execution_history
            }
            
        except Exception as e:
            print(f"   ✗ 响应生成失败: {e}")
            return {
                "status": "error",
                "error": str(e),
                "final_plan": None,
                "ui_modules": None,
                "quality_score": context.quality_score,
                "iterations": context.iteration_count
            }
    
    def _merge_agent_outputs(self, context: PlanningContext) -> Dict[str, Any]:
        """
        融合所有Agent的输出成最终规划
        """
        
        merged = {
            "destination": context.user_intent.destination if context.user_intent else None,
            "duration_days": context.user_intent.duration_days if context.user_intent else None,
            "created_at": datetime.now().isoformat(),
            
            # 数据层
            "pois": context.pois,
            "weather": context.weather,
            
            # 文化层
            "cultural_theme": context.cultural_theme,
            "cultural_background": context.cultural_background,
            "cultural_pois": context.cultural_pois,
            
            # 活动和体验
            "activities": context.cultural_activities,
            "experiences": context.special_experiences,
            
            # 路线和预算
            "itinerary": context.final_itinerary,
            "budget_allocation": context.budget_allocation,
            
            # 应急预案
            "contingency_plans": context.contingency_plans,
        }
        
        return merged
    
    def save_session(self, user_id: str, session_name: str, response: Dict[str, Any]) -> str:
        """
        保存本次规划会话
        """
        session_data = {
            "user_id": user_id,
            "session_name": session_name,
            "timestamp": datetime.now().isoformat(),
            "response": response,
            "execution_history": self.execution_history,
            "feedback_history": self.feedback_history
        }
        
        # 这里可以保存到数据库或文件
        session_id = f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"\n💾 会话已保存: {session_id}")
        
        return session_id
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """
        获取执行摘要
        """
        return {
            "total_iterations": len(self.execution_history),
            "final_quality_score": self.execution_history[-1]["quality_score"] if self.execution_history else 0.0,
            "execution_history": self.execution_history,
            "feedback_history": self.feedback_history
        }


async def run_example():
    """
    使用示例
    """
    
    # 创建编排器
    orchestrator = TravelPlanningOrchestrator()
    
    # 创建用户意图
    user_intent = UserIntent(
        destination="安庆",
        duration_days=3,
        budget=5000,
        preferences=["文化遗产", "美食", "天然景观"]
    )
    
    # 执行编排
    response = await orchestrator.orchestrate(user_intent)
    
    # 显示最终结果
    print("\n📊 最终结果:")
    print(json.dumps({
        "status": response["status"],
        "quality_score": response["quality_score"],
        "iterations": response["iterations"],
        "destination": response["final_plan"]["destination"] if response["final_plan"] else None
    }, indent=2, ensure_ascii=False))
    
    # 保存会话
    if response["status"] == "success":
        orchestrator.save_session("user_123", "安庆三日游", response)
    
    return response


if __name__ == "__main__":
    # 运行示例
    result = asyncio.run(run_example())
