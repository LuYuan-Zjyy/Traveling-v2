"""
小满 - 交互式引导 Agent (GuideAgent)
================================================================
职责：
  • 以友好拟人化的方式与用户多轮对话
  • 逐步收集旅行意图的关键槽位（目的地、天数、人数、预算、风格偏好）
  • 每轮对话先用轻量 LLM 调用提取结构化旅行信息(update_travel_info)
  • 再用更新后的状态构建 system prompt 进行正式回复
  • 信息充足后，通过 Function Calling 触发 start_planning

设计原则：
  • 两步调用策略：Step1 提取 → Step2 回复，避免单次调用不可靠
  • 槽位未满时持续追问，但语气轻松自然（像朋友聊天）
  • 前端 Chip 选择可直接更新 travel_info，不必经过 LLM
"""

from __future__ import annotations

import json
import traceback
from typing import Any, Dict, List, Optional


# ── 提取工具：轻量调用，仅用于 Step1 提取信息 ──
_UPDATE_TRAVEL_INFO_TOOL = {
    "type": "function",
    "function": {
        "name": "update_travel_info",
        "description": (
            "从用户最新的消息中提取旅行相关信息。"
            "只填写用户在本轮对话中明确提供或修改的字段，其余填 null。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "destination": {
                    "type": ["string", "null"],
                    "description": "目的地城市或地区",
                },
                "days": {
                    "type": ["integer", "null"],
                    "description": "旅行天数",
                },
                "people": {
                    "type": ["string", "null"],
                    "description": "出行人群描述，如'和女朋友''一家四口'",
                },
                "style": {
                    "type": ["string", "null"],
                    "description": "旅行风格，如'休闲''特种兵''文艺'",
                },
                "budget": {
                    "type": ["number", "null"],
                    "description": "总预算（人民币元）",
                },
                "preferences": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": "偏好标签列表，如['美食','历史文化']",
                },
                "special_requirements": {
                    "type": ["string", "null"],
                    "description": "特殊需求，如'带老人少爬山'",
                },
            },
            "required": [],
        },
    },
}

_EXTRACT_SYSTEM_PROMPT = (
    "你是旅行信息提取器。分析用户最新的消息，提取其中明确提到的旅行信息。"
    "调用 update_travel_info 工具，只填写本轮新出现或修改的字段，其余填 null。"
    "如果用户消息不包含任何旅行信息（如打招呼、闲聊），也调用工具但所有字段都填 null。"
)


# Function Calling 工具定义：LLM 认为信息收集完毕时调用此函数
_START_PLANNING_TOOL = {
    "type": "function",
    "function": {
        "name": "start_planning",
        "description": (
            "当已收集到用户旅行的关键信息（至少包含目的地和天数）后，"
            "调用此函数启动正式规划。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "destination": {
                    "type": "string",
                    "description": "目的地城市或地区",
                },
                "duration_days": {
                    "type": "integer",
                    "description": "旅行天数",
                },
                "budget": {
                    "type": "number",
                    "description": "总预算（人民币元），用户未说则填 0",
                },
                "people_count": {
                    "type": "integer",
                    "description": "出行人数，默认 1",
                },
                "preferences": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "偏好标签列表，如 ['美食', '历史文化']",
                },
                "travel_style": {
                    "type": "string",
                    "enum": ["relaxed", "balanced", "intense"],
                    "description": "旅行风格：relaxed=悠闲度假, balanced=平衡, intense=特种兵打卡",
                },
                "special_requirements": {
                    "type": "string",
                    "description": "特殊需求，如'带老人，少爬山'",
                },
            },
            "required": ["destination", "duration_days"],
        },
    },
}

# 系统提示词：定义小满的人设和行为规范
_SYSTEM_PROMPT = """你叫小满，是一位温暖贴心、见多识广的旅行定制师。你不只是在收集信息，更是真心实意地帮每一位旅行者找到最适合他们的旅程。

【你的性格】
- 你温柔而有洞察力，善于从用户的只言片语中感受到他们真正的期待和心情
- 你像一个贴心的朋友，在用户犹豫不决时给出真诚的建议，而不是冷冰冰地追问信息
- 你对每个目的地都充满热爱，会自然地分享一两句当地的迷人之处，让用户更加期待
- 你懂得照顾不同人群的感受：带老人出行需要注意什么，情侣想要什么样的氛围，独行者可能在寻找什么

【你的目标】
通过自然走心的对话了解用户的旅行需求，需要收集：
1. **目的地**（必须）：用户想去哪里
2. **天数**（必须）：玩几天
3. **人数**（可选）：几个人出行、什么关系
4. **预算**（可选）：大致预算范围
5. **偏好/风格**（可选）：喜欢什么类型，节奏快还是慢

【对话规则】
- 每轮最多追问 1-2 个问题，不要像填表一样一次问完
- 如果用户已经给了很多信息，就不要重复问
- 语气温暖真诚，适当用 emoji，像关心你的朋友在聊天
- 如果用户说了目的地但没说天数，优先问天数，但可以先对目的地表达你的真实感受（如"安庆啊，黄梅戏的故乡，好地方！"）
- 当至少收集到「目的地」和「天数」后，就可以调用 start_planning 工具开始规划
- 如果用户一次性给了足够信息（如"我想去上海玩3天"），直接调用 start_planning，不要多余追问
- 不要自己编造行程内容，你的职责只是收集信息
- 当用户问了其他的信息，优先回答用户的问题，之后将话题自然地转到下一个问题上
- 给出用户一般的建议和选项，但不要过早地给出具体的行程方案
- 没有收集到足够信息时，不要开始规划行程通过对话引导用户提供更多信息。
- 再进行规划之前，先检查一下用户提供的信息是否完整，如果不完整，继续通过对话引导用户提供更多信息。
- 尽量把问题控制在三个到四个之间，避免过多的对话轮次。
- 在进行规划之前，将信息反馈给用户，确认信息的准确性和完整性。
- 若是用户不明确地点，不想透露更多信息，直接随机规划行程

【人文关怀准则 — 想他人之所想】
- 如果用户提到带家人/老人，主动关心："老人家腿脚方便吗？我会特别注意安排不用爬太多台阶的路线 ☺️"
- 如果用户提到带孩子，主动想到："小朋友多大呀？我会帮你安排一些孩子也能玩得开心的地方~"
- 如果用户提到情侣/蜜月，营造浪漫期待："这趟旅行一定会很甜蜜！我帮你们安排一些特别有氛围的地方 💕"
- 如果用户表达了疲惫/想放松，给予温暖回应："听起来最近辛苦了，这次旅行就好好放松，我帮你规划一个不赶路的行程~"
- 如果用户表达了选择困难/犹豫，给出有温度的建议而非罗列选项
- 如果当地近期有特色节庆或时令亮点，可以自然提及，让用户感受到专属感
- 对话中体现"我在为你着想"的感觉，而不是机械地收集数据

【关于预算和人数】
- 如果用户没提预算，不必强行追问，可以在确认时温柔地说"预算方面有什么想法吗？没有的话我按舒适标准来安排~ 💰"
- 如果用户没提人数，默认 1 人

【第一条消息】
用户首次打开页面时，你会收到一条 "[系统] 用户已连接" 的消息。
此时请主动打招呼，语气温暖有亲和力，让用户感到被欢迎和期待。例如：
"嗨～我是小满 🌿 很高兴见到你！不管是想来一场说走就走的旅行，还是已经心里有了目的地，都可以跟我聊聊，我来帮你把旅途变得更特别 ✨ 你最近想去哪里看看呀？"
"""


class GuideAgent:
    """
    交互式引导 Agent（小满）

    不继承 TravelPlanningAgent 基类，因为它不参与规划迭代循环，
    而是一个独立的前置对话模块。

    Usage:
        agent = GuideAgent(llm_client)
        # 用户每发一条消息，调用一次 chat()
        result = agent.chat("我想去上海")
        # result = {"reply": "...", "is_ready": False, "intent": None}

        result = agent.chat("3天吧")
        # result = {"reply": "收到！...", "is_ready": True, "intent": {...}}
    """

    def __init__(self, llm_client):
        """
        Args:
            llm_client: DeepSeekClient 实例（需支持 chat_with_tools）
        """
        self.llm = llm_client
        self.conversation_history: List[Dict[str, str]] = []
        self._system_prompt_base = _SYSTEM_PROMPT
        # 旅行信息状态表：每轮对话由 LLM 通过 update_travel_info 工具更新
        self.travel_info: Dict[str, Any] = {
            "destination": None,
            "days": None,
            "people": None,
            "style": None,
            "budget": None,
            "preferences": None,
            "special_requirements": None,
        }

    def _build_system_messages(self) -> List[Dict[str, str]]:
        """构建带有当前已收集信息的 system prompt"""
        collected = {k: v for k, v in self.travel_info.items() if v is not None}
        if collected:
            info_parts = []
            label_map = {
                "destination": "目的地",
                "days": "天数",
                "people": "出行人群",
                "style": "旅行风格",
                "budget": "预算",
                "preferences": "偏好",
                "special_requirements": "特殊需求",
            }
            for k, v in collected.items():
                label = label_map.get(k, k)
                if isinstance(v, list):
                    v = "、".join(v)
                if k == "budget":
                    v = f"¥{v:.0f}"
                elif k == "days":
                    v = f"{v}天"
                info_parts.append(f"{label}：{v}")
            info_block = "[当前已收集信息]\n" + "\n".join(info_parts) + "\n\n请根据以上已收集信息继续引导对话，不要重复询问已知信息。\n\n"
        else:
            info_block = "[当前已收集信息]\n暂无，请通过对话收集用户的旅行需求。\n\n"

        full_prompt = info_block + self._system_prompt_base
        return [{"role": "system", "content": full_prompt}]

    def reset(self):
        """重置对话历史和旅行信息状态（新会话）"""
        self.conversation_history = []
        self.travel_info = {
            "destination": None,
            "days": None,
            "people": None,
            "style": None,
            "budget": None,
            "preferences": None,
            "special_requirements": None,
        }

    def restore_history(self, history: List[Dict[str, str]]):
        """
        恢复对话历史（断线重连时由后端调用）

        Args:
            history: [{"role": "user"/"assistant", "content": "..."}] 列表
        """
        self.conversation_history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in history
            if msg.get("role") in ("user", "assistant") and msg.get("content")
        ]

    def chat(self, user_message: str) -> Dict[str, Any]:
        """
        处理用户的一条消息（两步策略）

        Step 1: 轻量 LLM 调用 → 提取旅行信息 → 更新 travel_info 状态
        Step 2: 带更新状态的 system prompt → 正式对话 + start_planning 工具

        Returns:
            {
                "reply": str,
                "is_ready": bool,
                "intent": dict|None,
                "travel_info": dict
            }
        """
        self.conversation_history.append({
            "role": "user",
            "content": user_message,
        })

        # ── Step 1: 提取旅行信息（隐式，用户不可见）──
        if not user_message.startswith("[系统]"):
            self._extract_travel_info_from_conversation()

        # ── Step 2: 正式对话回复 ──
        messages = self._build_system_messages() + self.conversation_history

        try:
            response = self.llm.chat_with_tools(
                messages=messages,
                tools=[_START_PLANNING_TOOL],
                temperature=0.6,
                max_tokens=512,
            )
        except Exception as e:
            error_reply = "不好意思，网络打了个小盹 😅 你刚才说的是什么来着？再跟我说一次吧~"
            self.conversation_history.append({
                "role": "assistant",
                "content": error_reply,
            })
            return {"reply": error_reply, "is_ready": False, "intent": None,
                    "travel_info": self.get_travel_info()}

        tool_calls = response.get("tool_calls", [])
        content = response.get("content", "")

        # 检查是否触发了 start_planning
        for tc in tool_calls:
            if tc.get("name") == "start_planning":
                intent_data = tc.get("arguments", {})
                # 补充默认值
                intent_data.setdefault("people_count", 1)
                intent_data.setdefault("budget", 0)
                intent_data.setdefault("preferences", [])
                intent_data.setdefault("travel_style", "balanced")
                intent_data.setdefault("special_requirements", "")

                # 用 travel_info 补充 intent 中缺失的字段
                self._enrich_intent_from_travel_info(intent_data)

                confirm_text = content or self._build_confirm_text(intent_data)
                self.conversation_history.append({
                    "role": "assistant",
                    "content": confirm_text,
                })
                return {
                    "reply": confirm_text,
                    "is_ready": True,
                    "intent": intent_data,
                    "travel_info": self.get_travel_info(),
                }

        # 未触发规划 → 继续对话
        reply_text = content or "你可以告诉我想去哪里玩呀～"
        self.conversation_history.append({
            "role": "assistant",
            "content": reply_text,
        })
        return {
            "reply": reply_text,
            "is_ready": False,
            "intent": None,
            "travel_info": self.get_travel_info(),
        }

    # ── 私有方法 ──

    def _extract_travel_info_from_conversation(self):
        """
        Step 1: 用轻量 LLM 调用从最近对话中提取旅行信息
        只取最近几轮对话作为上下文，节省 tokens
        """
        recent_messages = self.conversation_history[-6:]  # 最近 3 轮
        extract_messages = [
            {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
        ] + recent_messages

        try:
            response = self.llm.chat_with_tools(
                messages=extract_messages,
                tools=[_UPDATE_TRAVEL_INFO_TOOL],
                temperature=0.1,
                max_tokens=200,
            )
            for tc in response.get("tool_calls", []):
                if tc.get("name") == "update_travel_info":
                    self._apply_travel_info_update(tc.get("arguments", {}))
                    print(f"[GuideAgent] travel_info 更新: {self.get_travel_info()}")
        except Exception as e:
            print(f"[GuideAgent] 信息提取失败(非致命): {e}")

    def _enrich_intent_from_travel_info(self, intent_data: Dict[str, Any]):
        """用 travel_info 中已收集的信息补充 start_planning 的 intent"""
        ti = self.travel_info
        if ti.get("budget") and not intent_data.get("budget"):
            intent_data["budget"] = ti["budget"]
        if ti.get("preferences") and not intent_data.get("preferences"):
            intent_data["preferences"] = ti["preferences"]
        if ti.get("special_requirements") and not intent_data.get("special_requirements"):
            intent_data["special_requirements"] = ti["special_requirements"]
        if ti.get("style") and intent_data.get("travel_style") == "balanced":
            style_map = {"休闲": "relaxed", "悠闲": "relaxed", "特种兵": "intense",
                         "打卡": "intense", "文艺": "balanced"}
            for k, v in style_map.items():
                if k in str(ti["style"]):
                    intent_data["travel_style"] = v
                    break
        if ti.get("people"):
            # 尝试从描述中推算人数
            people_str = str(ti["people"])
            if intent_data.get("people_count", 1) <= 1:
                if any(kw in people_str for kw in ["女朋友", "男朋友", "老婆", "老公", "对象"]):
                    intent_data["people_count"] = 2
                elif "一家" in people_str:
                    for ch in people_str:
                        if ch.isdigit():
                            intent_data["people_count"] = int(ch)
                            break

    def _apply_travel_info_update(self, update: Dict[str, Any]):
        """将 update_travel_info 工具返回的字段合并到 travel_info 状态"""
        for key in self.travel_info:
            if key in update and update[key] is not None:
                self.travel_info[key] = update[key]

    def get_travel_info(self) -> Dict[str, Any]:
        """获取当前旅行信息状态（过滤掉 None 值）"""
        return {k: v for k, v in self.travel_info.items() if v is not None}

    def _build_confirm_text(self, intent: Dict[str, Any]) -> str:
        """构建确认出发的文本"""
        dest = intent.get("destination", "")
        days = intent.get("duration_days", 3)
        people = intent.get("people_count", 1)
        budget = intent.get("budget", 0)
        style = intent.get("travel_style", "balanced")

        style_map = {
            "relaxed": "悠闲舒适",
            "balanced": "劳逸结合",
            "intense": "特种兵打卡",
        }
        style_text = style_map.get(style, "劳逸结合")

        parts = [f"太好了！**{dest} {days}天**，这趟旅行一定会很精彩 ✨"]
        if people > 1:
            parts.append(f"\n{people}个人一起出发")
        if budget > 0:
            parts.append(f"，预算 ¥{budget:.0f}")
        parts.append(f"，{style_text}的节奏")
        parts.append("。\n\n我现在就去帮你安排，会尽量把每一天都安排得恰到好处～请稍等一小会儿 🗺️")

        return "".join(parts)

    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取完整对话历史"""
        return list(self.conversation_history)
