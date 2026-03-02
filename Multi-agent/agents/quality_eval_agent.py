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
    
    # 偏好关键词语义映射: 偏好标签 -> 相关关键词列表
    _PREF_KEYWORDS = {
        "美食": ["餐", "食", "美食", "restaurant", "dining", "food", "菜", "小吃", "饮食"],
        "历史文化": ["历史", "文化", "博物馆", "museum", "古", "遗址", "temple", "寺", "祠", "故居", "纪念"],
        "文化": ["文化", "culture", "历史", "博物馆", "戏曲", "非遗", "民俗", "艺术", "传统"],
        "自然风光": ["自然", "nature", "山", "forest", "park", "公园", "湖", "river", "景区", "风景", "瀑布", "峡谷"],
        "户外运动": ["户外", "outdoor", "hiking", "爬山", "山", "adventure", "攀岩", "徒步"],
        "亲子": ["亲子", "family", "children", "游乐", "乐园", "儿童"],
        "乡村体验": ["乡村", "农村", "田园", "农家", "村落", "古镇", "民居"],
        "购物": ["购物", "shopping", "商场", "市场", "街", "店"],
        "摄影": ["摄影", "photo", "风景", "景色", "观光"],
    }

    def _evaluate_user_fit(self, context: PlanningContext) -> float:
        """
        评估用户匹配度：是否符合用户偏好

        使用语义关键词映射 + 全文语料库匹配，避免直接字符串比较失败。
        每个偏好只计一次（修复双重计数问题）。
        """
        score = 0.5  # 默认分数

        if not context.user_intent:
            return score

        preferences = context.user_intent.preferences or []
        if not preferences:
            return score

        # 构建全文语料库（主题 + POI名称/类别/描述 + 活动名称）
        corpus_tokens: List[str] = []
        if context.cultural_theme:
            corpus_tokens.append(context.cultural_theme.lower())
        for poi in context.cultural_pois:
            if isinstance(poi, dict):
                corpus_tokens.append(poi.get("name", "").lower())
                corpus_tokens.append(poi.get("category", "").lower())
                corpus_tokens.append((poi.get("description") or "").lower())
            else:
                corpus_tokens.append(getattr(poi, "name", "").lower())
                corpus_tokens.append(getattr(poi, "category", "").lower())
                corpus_tokens.append((getattr(poi, "description", "") or "").lower())
        for act in context.cultural_activities:
            if isinstance(act, dict):
                corpus_tokens.append(act.get("activity", "").lower())
                corpus_tokens.append(act.get("type", "").lower())
                corpus_tokens.append(act.get("name", "").lower())
        corpus_text = " ".join(corpus_tokens)

        # 每个偏好只计一次匹配，修复双重计数问题
        matched = 0
        for pref in preferences:
            pref_lower = pref.lower()
            found = False

            # 直接子串匹配
            if pref_lower in corpus_text:
                found = True

            # 语义关键词映射匹配
            if not found:
                keywords = self._PREF_KEYWORDS.get(pref, [])
                for kw in keywords:
                    if kw in corpus_text:
                        found = True
                        break

            # 类别占位匹配：美食类偏好 → 是否有餐厅POI；自然类 → 是否有景区
            if not found:
                if any(k in pref_lower for k in ["美食", "food", "餐"]):
                    found = any(
                        any(k in str(p).lower() for k in ["餐", "食", "restaurant"])
                        for p in context.cultural_pois
                    )
                elif any(k in pref_lower for k in ["自然", "nature", "风光"]):
                    found = any(
                        any(k in str(p).lower() for k in ["山", "湖", "公园", "景区", "park"])
                        for p in context.cultural_pois
                    )

            if found:
                matched += 1

        user_fit = matched / len(preferences)
        score = 0.3 + (user_fit * 0.7)

        # ── 额加检查：用户明确点名的地点是否实际出现在行程中 ──
        # 反馈逻辑：每个未安排的用户点名地点扣 0.2（上限拣去 0.4）
        user_mentioned = getattr(context, 'user_mentioned_pois', []) or []
        if user_mentioned and context.final_itinerary:
            itinerary_text = " ".join(
                p.get("name", "")
                for day_route in context.final_itinerary.get("routes", [])
                for p in day_route.get("pois", [])
            )
            missing = [
                name for name in user_mentioned
                if not any(name[:3] in wp for wp in itinerary_text.split())
                and name not in itinerary_text
            ]
            if missing:
                penalty = min(0.4, len(missing) * 0.2)
                score = max(0.0, score - penalty)
                print(f"  用户点名地点未安排: {missing} → user_fit -{penalty:.1f}")

        return min(1.0, score)
    
    def _evaluate_experience_quality(self, context: PlanningContext) -> float:
        """
        评估体验质量：规划的体验质量如何
        增加对实际行程的检验（丢天、公共设施缺少等）
        """
        score = 0.5  # 默认分数

        # 检查是否有特色体验设计
        if context.cultural_background:
            score += 0.1  # 有文化背景说明（权重从 0.2 降至 0.1）

        # 检查是否有多样化活动
        if len(context.cultural_activities) >= 3:
            score += 0.1  # 活动丰富（权重从 0.2 降至 0.1）

        # ── 新增：检查实际行程天数是否匹配 ──
        expected_days = context.user_intent.duration_days if context.user_intent else 0
        if expected_days and context.optimized_routes:
            actual_days = len(context.optimized_routes)
            if actual_days >= expected_days:
                score += 0.2  # 天数充足
            elif actual_days >= expected_days - 1:
                score += 0.1  # 少一天还可接受
            # 否则：行程天数不足， experience_quality 不加分 → 干预迭代

        # ── 新增：检查每天景点数量（若某天少于 2 个，认为偶尔行程稀疏） ──
        if context.optimized_routes:
            sparse_days = sum(
                1 for r in context.optimized_routes
                if len(r.get("pois", [])) < 2
            )
            if sparse_days == 0:
                score += 0.1  # 每天景点充实
            elif sparse_days <= 1:
                score += 0.05  # 仅一天稀疏

        # 检查是否有应急预案
        if context.contingency_plans and len(context.contingency_plans) > 0:
            score += 0.05  # 有备选方案（权重从 0.1 降至 0.05）

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
        """为特定Agent生成可执行反馈（修复：之前反馈触发条件与实际评分脱节，导致死代码）"""
        feedback = {}

        # ── 1. 用户明确点名的地点遗漏 → 触发路线重新规划 ──
        user_mentioned = getattr(context, 'user_mentioned_pois', []) or []
        if user_mentioned and context.final_itinerary:
            itinerary_text = " ".join(
                p.get("name", "")
                for day_route in context.final_itinerary.get("routes", [])
                for p in day_route.get("pois", [])
            )
            missing = [
                name for name in user_mentioned
                if not any(name[:3] in wp for wp in itinerary_text.split())
                and name not in itinerary_text
            ]
            if missing:
                feedback["route_agent"] = {
                    "status": "feedback_needed",
                    "issue": f"用户明确点名的地点未在行程中出现: {missing}",
                    "missing_pois": missing,
                    "suggestions": [
                        f"确保 {', '.join(missing)} 必须出现在至少一天的行程中",
                        "这些地点已被标记为 rating=5.5，路线规划时应优先分配",
                    ]
                }

        # ── 2. 行程天数不足 → 触发路线重新规划 ──
        expected_days = context.user_intent.duration_days if context.user_intent else 0
        actual_days = len(context.optimized_routes or [])
        if expected_days and actual_days < expected_days - 1:
            existing = feedback.get("route_agent", {})
            existing.update({
                "status": "feedback_needed",
                "issue": existing.get("issue", "") + f" | 行程天数不足({actual_days}/{expected_days}天)",
                "day_shortage": expected_days - actual_days,
            })
            feedback["route_agent"] = existing

        # ── 3. 完整性不足 → 扩大数据采集（仅第二轮以后避免第一轮就立刻重搜） ──
        if scores.get("completeness", 1.0) < 0.6 and context.iteration_count > 1:
            feedback["data_collection_agent"] = {
                "status": "feedback_needed",
                "issue": "数据不足（完整性评分低），需要扩大搜索范围",
                "expand_search": True,
            }

        # ── 4. 预算超支 → 触发预算重新规划 ──
        if context.budget_allocation and context.user_intent:
            total_budget = sum(context.budget_allocation.values())
            if total_budget > context.user_intent.budget * 1.05:
                feedback["budget_agent"] = {
                    "status": "feedback_needed",
                    "issue": f"总预算超支¥{(total_budget - context.user_intent.budget):.0f}",
                    "suggestions": [
                        "检查门票数据是否来自行程内景点（应已修复）",
                        "考虑降低住宿等级或减少餐饮预算",
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
