"""
质量评估Agent - 检查规划方案是否符合要求
负责对其他Agent的输出进行质量评估和建议改进
"""

from typing import Dict, List, Any, Optional
from core.base_agent import TravelPlanningAgent
from core.planning_context import PlanningContext, AgentOutput


class QualityEvalAgent(TravelPlanningAgent):
    """
    质量评估Agent
    
    职责：
    • 检查规划方案是否满足用户要求
    • 识别潜在的问题和冲突
    • 评估整体质量并给出评分
    • 提出改进建议
    • 决定是否需要继续迭代
    """
    
    def __init__(self):
        super().__init__(name="quality_eval_agent")
        
        # 评估权重
        self.weights = {
            "completeness": 0.25,      # 完整性
            "feasibility": 0.25,       # 可行性
            "user_fit": 0.25,          # 符合用户需求
            "experience_quality": 0.25  # 体验质量
        }
    
    def _validate_input(self, context: PlanningContext) -> bool:
        """验证输入数据"""
        # 需要检查前面Agent的输出
        if not context.agent_outputs:
            return False
        
        return True
    
    def _execute_core(self, context: PlanningContext) -> Dict[str, Any]:
        """
        核心业务逻辑：质量评估
        
        流程：
        1. 评估完整性 - 是否收集了所有必需数据
        2. 评估可行性 - 方案是否在预算和时间内可行
        3. 评估用户匹配度 - 是否符合用户偏好
        4. 评估体验质量 - 规划的体验质量如何
        5. 生成改进建议
        """
        
        result = {
            "overall_score": 0.0,
            "is_acceptable": False,
            "scores": {},
            "issues": [],
            "suggestions": [],
            "feedback_per_agent": {},
            "status": "success"
        }
        
        try:
            # Step 1: 评估完整性
            completeness_score = self._evaluate_completeness(context)
            result["scores"]["completeness"] = completeness_score
            print(f"  完整性评分: {completeness_score:.2f}")
            
            # Step 2: 评估可行性
            feasibility_score = self._evaluate_feasibility(context)
            result["scores"]["feasibility"] = feasibility_score
            print(f"  可行性评分: {feasibility_score:.2f}")
            
            # Step 3: 评估用户匹配度
            user_fit_score = self._evaluate_user_fit(context)
            result["scores"]["user_fit"] = user_fit_score
            print(f"  用户匹配度: {user_fit_score:.2f}")
            
            # Step 4: 评估体验质量
            quality_score = self._evaluate_experience_quality(context)
            result["scores"]["experience_quality"] = quality_score
            print(f"  体验质量: {quality_score:.2f}")
            
            # Step 5: 计算综合评分
            overall_score = (
                completeness_score * self.weights["completeness"] +
                feasibility_score * self.weights["feasibility"] +
                user_fit_score * self.weights["user_fit"] +
                quality_score * self.weights["experience_quality"]
            )
            result["overall_score"] = round(overall_score, 2)
            
            # Step 6: 判断是否可接受
            result["is_acceptable"] = overall_score >= 0.75
            print(f"\n✓ 综合评分: {overall_score:.2f}/1.0")
            print(f"✓ 可接受: {result['is_acceptable']}")
            
            # Step 7: 生成改进建议
            suggestions = self._generate_suggestions(context, result["scores"])
            result["suggestions"] = suggestions
            
            # Step 8: 为特定Agent生成反馈
            feedback = self._generate_agent_feedback(context, result["scores"])
            result["feedback_per_agent"] = feedback
            
            # 学习
            self.learn_and_store({
                "type": "quality_evaluation",
                "overall_score": overall_score,
                "is_acceptable": result["is_acceptable"],
                "iteration": context.iteration_count
            })
            
            return result
            
        except Exception as e:
            print(f"✗ 质量评估失败: {e}")
            self.memory.add_error(str(e), {}, self.current_iteration)
            result["status"] = "error"
            result["error"] = str(e)
            return result
    
    def _evaluate_completeness(self, context: PlanningContext) -> float:
        """
        评估完整性：是否收集了所有必需数据
        
        检查项：
        • 是否获取了POI数据
        • 是否进行了文化分析
        • 是否规划了路线
        • 是否做了预算估算
        """
        score = 0.0
        max_score = 4.0
        
        # 检查数据采集
        if context.pois and len(context.pois) > 0:
            score += 1.0
        
        # 检查文化分析
        if context.cultural_pois and len(context.cultural_pois) > 0:
            score += 1.0
        
        # 检查路线规划
        if context.optimized_routes and len(context.optimized_routes) > 0:
            score += 1.0
        
        # 检查预算规划
        if context.budget_allocation:
            score += 1.0
        
        return score / max_score
    
    def _evaluate_feasibility(self, context: PlanningContext) -> float:
        """
        评估可行性：方案是否在时间和预算内可行
        """
        score = 0.5  # 默认分数
        
        # 检查预算
        if context.budget_allocation and context.user_intent:
            budget_used = sum(context.budget_allocation.values())
            if budget_used <= context.user_intent.budget:
                score += 0.3  # 在预算内
            elif budget_used <= context.user_intent.budget * 1.1:
                score += 0.15  # 稍微超预算
            # 否则质量不会增加
        
        # 检查时间可行性
        if context.final_itinerary and context.user_intent:
            total_time = context.final_itinerary.get("total_hours", 0)
            available_time = context.user_intent.duration_days * 8  # 每天8小时游览时间
            
            if total_time <= available_time:
                score += 0.2  # 时间充足
            elif total_time <= available_time * 1.2:
                score += 0.1  # 时间紧张但可行
        
        return min(1.0, score)
    
    def _evaluate_user_fit(self, context: PlanningContext) -> float:
        """
        评估用户匹配度：是否符合用户偏好
        """
        score = 0.5  # 默认分数
        
        if not context.user_intent:
            return score
        
        preferences = context.user_intent.preferences or []
        
        # 检查是否包含用户想要的体验
        cultural_pois = [poi.get("name", "") for poi in context.cultural_pois]
        activities = [act.get("activity", "") for act in context.cultural_activities]
        
        # 计算匹配的偏好
        matched_preferences = 0
        for pref in preferences:
            pref_lower = pref.lower()
            
            # 检查POI
            for poi_name in cultural_pois:
                if pref_lower in poi_name.lower() or poi_name.lower() in pref_lower:
                    matched_preferences += 1
                    break
            
            # 检查活动
            for act_name in activities:
                if pref_lower in act_name.lower() or act_name.lower() in pref_lower:
                    matched_preferences += 1
                    break
        
        if preferences:
            user_fit = matched_preferences / len(preferences)
            score = 0.3 + (user_fit * 0.7)  # 权重为30% + 70%
        
        return min(1.0, score)
    
    def _evaluate_experience_quality(self, context: PlanningContext) -> float:
        """
        评估体验质量：规划的体验质量如何
        """
        score = 0.5  # 默认分数
        
        # 检查是否有特色体验设计
        if context.cultural_background:
            score += 0.2  # 有文化背景说明
        
        # 检查是否有多样化活动
        if len(context.cultural_activities) >= 3:
            score += 0.2  # 活动丰富
        
        # 检查是否有应急预案
        if context.contingency_plans and len(context.contingency_plans) > 0:
            score += 0.1  # 有备选方案
        
        return min(1.0, score)
    
    def _generate_suggestions(self, context: PlanningContext, 
                            scores: Dict[str, float]) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        # 根据得分低的项目提供建议
        if scores.get("completeness", 1.0) < 0.8:
            suggestions.append("需要补充更多的目的地数据信息")
        
        if scores.get("feasibility", 1.0) < 0.8:
            if context.budget_allocation:
                budget_exceed = sum(context.budget_allocation.values()) - context.user_intent.budget
                if budget_exceed > 0:
                    suggestions.append(f"预算可能超支¥{budget_exceed:.0f}，建议调整项目")
        
        if scores.get("user_fit", 1.0) < 0.8:
            suggestions.append("建议调整景点选择以更好地匹配用户偏好")
        
        if scores.get("experience_quality", 1.0) < 0.8:
            suggestions.append("建议增加更多特色文化体验内容")
        
        # 通用建议
        if not context.contingency_plans or len(context.contingency_plans) == 0:
            suggestions.append("建议补充应急预案和备选方案")
        
        if not context.cultural_background or len(context.cultural_background) == 0:
            suggestions.append("建议补充景点的文化背景说明")
        
        return suggestions[:3]  # 返回前3个建议
    
    def _generate_agent_feedback(self, context: PlanningContext, 
                                scores: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
        """为特定Agent生成反馈"""
        feedback = {}
        
        # 给CultureAgent的反馈
        if scores.get("user_fit", 1.0) < 0.75:
            feedback["culture_agent"] = {
                "status": "feedback_needed",
                "issue": "文化景点选择不够符合用户偏好",
                "suggestions": [
                    "检查用户偏好列表",
                    "确保至少包含1个用户特别想要的体验",
                    "增加更多相关的特色活动"
                ]
            }
        
        # 给RouteAgent的反馈
        if scores.get("feasibility", 1.0) < 0.75:
            feedback["route_agent"] = {
                "status": "feedback_needed",
                "issue": "路线规划不够合理或时间紧张",
                "suggestions": [
                    "检查每个景点的停留时间",
                    "优化景点间的路线",
                    "考虑删除时间消耗最多但用户不感兴趣的景点"
                ]
            }
        
        # 给BudgetAgent的反馈
        if context.budget_allocation:
            total_budget = sum(context.budget_allocation.values())
            if total_budget > context.user_intent.budget * 1.05:
                feedback["budget_agent"] = {
                    "status": "feedback_needed",
                    "issue": f"总预算超支¥{(total_budget - context.user_intent.budget):.0f}",
                    "suggestions": [
                        "检查每项成本是否合理",
                        "考虑使用折扣或优惠",
                        "调整住宿或餐饮等级"
                    ]
                }
        
        return feedback
    
    def generate_summary(self, context: PlanningContext) -> str:
        """生成质量评估摘要"""
        score = context.quality_score
        
        if score >= 0.9:
            return "✅ 优秀方案 - 完全符合用户需求，体验质量很高"
        elif score >= 0.75:
            return "⭐ 好方案 - 大体符合要求，可能略需调整"
        elif score >= 0.6:
            return "🟡 一般方案 - 需要改进几个方面"
        else:
            return "🔴 需要重新规划 - 存在较多问题"
