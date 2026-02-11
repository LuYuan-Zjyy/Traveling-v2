"""
主控Agent (Orchestrator)
实现: 意图识别 → 任务分解(调MCP) → 协调调度(规划路线)

对应 Agent构建指南.md 第50-57行:
  🎯 主控Agent (Orchestrator)
  职责：任务理解 → 任务分解 → Agent调度 → 结果整合 → 输出生成
  核心能力：
  • 用户意图识别        • 任务规划与分解
  • 多Agent协调调度     • 冲突检测与解决
  • 结果融合与优化      • 质量把控与兜底
"""

import json
import time
from typing import Optional

from orchestrator.config import AgentConfig, load_config
from orchestrator.deepseek_client import DeepSeekClient
from orchestrator.amap_tools import AmapTools, TOOL_DEFINITIONS
from orchestrator.result_store import PlanningSession, ResultStore
from orchestrator.prompts import (
    SYSTEM_PROMPT,
    INTENT_RECOGNITION_PROMPT,
    TASK_DECOMPOSITION_PROMPT,
    PLAN_GENERATION_PROMPT,
    STRUCTURED_PLAN_PROMPT,
)


class TravelOrchestrator:
    """
    主控Agent: DeepSeek + 高德MCP

    工作流程:
      用户输入(旅游意图)
          ↓
      [1] 意图识别 - DeepSeek解析用户自然语言
          ↓
      [2] 任务分解 - DeepSeek Function Calling → 调用高德MCP工具
          ↓
      [3] 协调调度 - 基于真实数据生成完整规划方案
          ↓
      规划方案(文本输出)
    """

    # 最大工具调用轮数(防死循环)
    MAX_TOOL_ROUNDS = 8

    def __init__(self, config: Optional[AgentConfig] = None,
                 store: Optional[ResultStore] = None):
        self.config = config or load_config()

        # 初始化组件
        self.llm = DeepSeekClient(
            api_key=self.config.deepseek.api_key,
            base_url=self.config.deepseek.base_url,
            model=self.config.deepseek.model,
        )
        self.tools = AmapTools(
            api_key=self.config.amap.api_key,
        )

        # 结果存储
        self.store = store or ResultStore()

        # 运行时状态
        self._intent: Optional[dict] = None
        self._collected_data: list[dict] = []
        self._last_session: Optional[PlanningSession] = None

    # ==============================================================
    # 公共接口
    # ==============================================================

    def plan(self, user_input: str) -> str:
        """
        完整规划流程: 输入旅游意图 → 输出规划方案(文本)

        所有中间结果和最终输出都会自动存储到 outputs/ 目录,
        便于后续使用 TravelPlanner / TripTailor 评测脚本评分.

        Args:
            user_input: 用户的自然语言旅游需求

        Returns:
            旅行规划方案 (Markdown 文本)
        """
        # 重置状态
        self._intent = None
        self._collected_data = []

        # 创建会话记录
        session = PlanningSession()
        session.begin(user_input, model=self.config.deepseek.model)

        print("=" * 60)
        print("  [AGENT] 主控Agent 开始工作")
        print("=" * 60)

        try:
            # Step 1: 意图识别
            print("\n[STEP 1/4] 意图识别...")
            intent = self._recognize_intent(user_input)
            self._intent = intent
            session.record_intent(intent)
            print(f"   [OK] 识别完成:")
            print(f"      目的地: {intent.get('destination', '未知')}")
            print(f"      天数: {intent.get('duration_days', '未知')}")
            print(f"      预算: {intent.get('budget', '不限')}")
            print(f"      偏好: {intent.get('preferences', [])}")

            # Step 2: 任务分解 + 工具调用
            print("\n[STEP 2/4] 任务分解 & MCP工具调用...")
            collected_data = self._decompose_and_execute(intent, session)
            self._collected_data = collected_data
            print(f"   [OK] 数据收集完成, 共{len(collected_data)}条信息")

            # Step 3: 协调调度 - 生成规划 (Markdown 文本)
            print("\n[STEP 3/4] 协调调度 & 生成规划方案...")
            plan_text = self._generate_plan(intent, collected_data)
            print("   [OK] 规划方案已生成")

            # Step 4: 生成结构化 JSON (供评测使用)
            print("\n[STEP 4/4] 生成结构化规划数据 (用于评测)...")
            plan_structured = self._generate_structured_plan(intent, collected_data)
            if plan_structured:
                print("   [OK] 结构化数据已生成")
            else:
                print("   [WARN] 结构化数据生成失败，仅保存原始文本")

            # 记录结果并保存
            session.record_plan(plan_raw=plan_text, plan_structured=plan_structured)
            session.finish(success=True)

        except Exception as e:
            session.finish(success=False, error=str(e))
            raise
        finally:
            # 无论成功与否都保存会话
            session_dir = self.store.save_session(session)
            self._last_session = session
            print(f"\n[SAVE] 会话已保存: {session_dir}")

        print("\n" + "=" * 60)
        print("  [DONE] 规划完成!")
        print("=" * 60)

        return plan_text

    # ==============================================================
    # Step 1: 意图识别
    # ==============================================================

    def _recognize_intent(self, user_input: str) -> dict:
        """
        调用 DeepSeek 解析用户自然语言, 提取结构化的旅行意图

        Returns:
            dict: 结构化的意图信息
        """
        prompt = INTENT_RECOGNITION_PROMPT.format(user_input=user_input)

        response = self.llm.chat(
            messages=[
                {"role": "system", "content": "你是旅行意图分析专家。请严格返回JSON格式。"},
                {"role": "user", "content": prompt},
            ],
            temperature=self.config.deepseek.temperature,
        )

        # 提取 JSON
        intent = self.llm.extract_json(response)
        if intent is None:
            # 降级: 至少提取目的地
            intent = {
                "destination": user_input,
                "duration_days": 3,
                "preferences": [],
                "raw_response": response,
            }

        return intent

    # ==============================================================
    # Step 2: 任务分解 + MCP工具调用 (核心 Agent Loop)
    # ==============================================================

    def _decompose_and_execute(self, intent: dict,
                               session: Optional[PlanningSession] = None) -> list[dict]:
        """
        让 DeepSeek 通过 Function Calling 自主决定调用哪些高德工具,
        执行工具后把结果反馈给 DeepSeek, 循环直到收集够信息。

        这是一个标准的 ReAct 循环:
        Thought → Action (Tool Call) → Observation → Thought → ...

        Args:
            intent: 结构化意图
            session: 可选的会话记录器, 用于持久化每一次工具调用

        Returns:
            list[dict]: 收集到的所有工具调用结果
        """
        collected = []
        intent_json = json.dumps(intent, ensure_ascii=False, indent=2)

        # 构建初始消息
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": TASK_DECOMPOSITION_PROMPT.format(intent_json=intent_json)},
        ]

        for round_num in range(self.MAX_TOOL_ROUNDS):
            # 让 DeepSeek 决定下一步行动
            result = self.llm.chat_with_tools(
                messages=messages,
                tools=TOOL_DEFINITIONS,
                temperature=self.config.deepseek.temperature,
            )

            # 如果没有工具调用, 说明 DeepSeek 认为信息已经够了
            if not result["tool_calls"]:
                if result["content"]:
                    print(f"   [LLM] Agent: {result['content'][:100]}...")
                break

            # 把 assistant 的回复(含 tool_calls) 加入消息历史
            messages.append(self._build_assistant_message(result))

            # 执行每个工具调用
            for tool_call in result["tool_calls"]:
                tool_name = tool_call["name"]
                tool_args = tool_call["arguments"]
                tool_id = tool_call["id"]

                print(f"   [TOOL] 调用工具: {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:80]})")

                # 调用高德MCP工具 (记录耗时)
                t0 = time.time()
                tool_result = self.tools.call_tool(tool_name, tool_args)
                duration_ms = int((time.time() - t0) * 1000)

                # 记录结果
                collected.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result": tool_result,
                })

                # 记录到会话 (持久化)
                if session:
                    session.record_tool_call(
                        tool_name, tool_args, tool_result, duration_ms
                    )

                # 工具结果反馈给 DeepSeek
                tool_result_str = json.dumps(tool_result, ensure_ascii=False)
                # 截断过长的结果
                if len(tool_result_str) > 3000:
                    tool_result_str = tool_result_str[:3000] + "...(截断)"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_id,
                    "content": tool_result_str,
                })

                if "error" in tool_result:
                    print(f"   [WARN] 工具返回错误: {tool_result['error']}")
                else:
                    count = tool_result.get("count", "")
                    print(f"   [OK] 返回{count}条结果 ({duration_ms}ms)" if count else f"   [OK] 返回成功 ({duration_ms}ms)")

        return collected

    # ==============================================================
    # Step 3: 协调调度 - 生成最终规划方案
    # ==============================================================

    def _generate_plan(self, intent: dict, collected_data: list[dict]) -> str:
        """
        基于意图和收集到的真实数据, 调用 DeepSeek 生成完整的规划方案

        Returns:
            str: Markdown格式的规划方案文本
        """
        intent_json = json.dumps(intent, ensure_ascii=False, indent=2)

        # 整理收集到的数据, 按类型分组
        data_summary = self._summarize_collected_data(collected_data)

        prompt = PLAN_GENERATION_PROMPT.format(
            intent_json=intent_json,
            collected_data=data_summary,
        )

        plan = self.llm.chat(
            messages=[
                {"role": "system", "content": "你是专业旅行规划师。请基于真实数据生成详细可执行的旅行方案。"},
                {"role": "user", "content": prompt},
            ],
            temperature=self.config.deepseek.planning_temperature,
            max_tokens=self.config.deepseek.max_tokens,
        )

        return plan

    # ==============================================================
    # Step 4: 生成结构化 JSON (供评测)
    # ==============================================================

    def _generate_structured_plan(self, intent: dict,
                                  collected_data: list[dict]) -> Optional[dict]:
        """
        让 DeepSeek 基于同样的信息输出结构化 JSON 规划,
        格式兼容 TripTailor 评测框架:

        {
            "hotel": [{"day": 1, "name": "...", "price_per_night": N}],
            "transportation": [{"day": 1, "mode": "Train/Flight", ...}],
            "itinerary": {
                "day_1": [{"time": "HH:MM-HH:MM", "location": "...",
                           "price": N, "action": "sightseeing/dining"}]
            }
        }

        Returns:
            结构化规划 dict, 解析失败时返回 None
        """
        intent_json = json.dumps(intent, ensure_ascii=False, indent=2)
        data_summary = self._summarize_collected_data(collected_data)

        prompt = STRUCTURED_PLAN_PROMPT.format(
            intent_json=intent_json,
            collected_data=data_summary,
        )

        response = self.llm.chat(
            messages=[
                {"role": "system", "content": "你是旅行数据结构化专家。请严格以JSON格式返回结果，不要添加任何额外文字。"},
                {"role": "user", "content": prompt},
            ],
            temperature=self.config.deepseek.temperature,
            max_tokens=self.config.deepseek.max_tokens,
        )

        structured = self.llm.extract_json(response)

        # 基本校验
        if structured and isinstance(structured, dict):
            # 确保核心字段存在
            if "itinerary" not in structured:
                structured["itinerary"] = {}
            if "hotel" not in structured:
                structured["hotel"] = []
            if "transportation" not in structured:
                structured["transportation"] = []
            return structured

        return None

    # ==============================================================
    # 辅助方法
    # ==============================================================

    def _build_assistant_message(self, result: dict) -> dict:
        """构建包含 tool_calls 的 assistant 消息"""
        msg = {"role": "assistant", "content": result["content"] or ""}

        if result["tool_calls"]:
            msg["tool_calls"] = []
            for tc in result["tool_calls"]:
                msg["tool_calls"].append({
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                })

        return msg

    def _summarize_collected_data(self, collected_data: list[dict]) -> str:
        """将收集到的工具结果整理为可读文本"""
        sections = {
            "geocode": "### [GEO] 地理位置信息",
            "search_pois": "### [POI] 搜索到的地点",
            "search_around": "### [NEAR] 周边搜索结果",
            "query_weather": "### [WEATHER] 天气信息",
            "route_driving": "### [DRIVE] 驾车路线",
            "route_transit": "### [TRANSIT] 公交路线",
            "route_walking": "### [WALK] 步行路线",
            "regeocode": "### [ADDR] 地址信息",
        }

        grouped: dict[str, list] = {}
        for item in collected_data:
            tool = item["tool"]
            if tool not in grouped:
                grouped[tool] = []
            grouped[tool].append(item)

        lines = []
        for tool_name, items in grouped.items():
            header = sections.get(tool_name, f"### [TOOL] {tool_name}")
            lines.append(header)

            for item in items:
                args_str = json.dumps(item["args"], ensure_ascii=False)
                result = item["result"]

                lines.append(f"\n**查询: {args_str}**")

                if "error" in result:
                    lines.append(f"- [WARN] 错误: {result['error']}")
                else:
                    result_str = json.dumps(result, ensure_ascii=False, indent=2)
                    # 限制长度
                    if len(result_str) > 1500:
                        result_str = result_str[:1500] + "\n...(更多结果已截断)"
                    lines.append(f"```json\n{result_str}\n```")

            lines.append("")

        return "\n".join(lines) if lines else "（未收集到数据）"

    # ==============================================================
    # 便捷属性
    # ==============================================================

    @property
    def last_intent(self) -> Optional[dict]:
        """最近一次识别的意图"""
        return self._intent

    @property
    def last_collected_data(self) -> list[dict]:
        """最近一次收集的工具数据"""
        return self._collected_data

    @property
    def last_session(self) -> Optional[PlanningSession]:
        """最近一次规划会话 (含完整中间数据)"""
        return self._last_session

