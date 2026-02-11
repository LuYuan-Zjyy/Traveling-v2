"""
结果存储模块 (Result Store)

系统性地存储 Agent 的每一次规划过程和结果，包括：
  - 用户原始输入
  - 意图识别结果
  - 工具调用记录（每一次 MCP 调用的参数和返回值）
  - 原始规划文本（Markdown）
  - 结构化规划 JSON（用于评测）
  - 会话元数据（时间、模型、耗时等）

存储结构:
  orchestrator/outputs/
  ├── sessions/                     # 每次规划的完整会话数据
  │   └── {session_id}/
  │       ├── meta.json             # 会话元数据
  │       ├── intent.json           # 意图识别结果
  │       ├── tool_calls.json       # 工具调用记录
  │       ├── plan_raw.md           # 原始规划方案（Markdown）
  │       └── plan_structured.json  # 结构化规划 JSON
  ├── exports/                      # 评测导出目录
  │   ├── travelplanner/            # TravelPlanner 评测格式
  │   └── triptailor/               # TripTailor 评测格式
  └── history.jsonl                 # 历史记录索引（追加写入）
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class PlanningSession:
    """
    单次规划会话的数据容器

    从 orchestrator.plan() 的执行过程中逐步填充数据,
    最终调用 save() 持久化到磁盘.
    """

    def __init__(self, session_id: str = None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.created_at = datetime.now().isoformat()

        # ---- 输入 ----
        self.user_input: str = ""

        # ---- Step 1: 意图识别 ----
        self.intent: Optional[dict] = None

        # ---- Step 2: 工具调用 ----
        self.tool_calls: list[dict] = []
        # 每条: {"tool": str, "args": dict, "result": dict, "timestamp": str, "duration_ms": int}

        # ---- Step 3: 规划输出 ----
        self.plan_raw: str = ""           # Markdown 原始文本
        self.plan_structured: Optional[dict] = None  # 结构化 JSON (用于评测)

        # ---- 元数据 ----
        self.model: str = ""
        self.start_time: float = 0
        self.end_time: float = 0
        self.success: bool = False
        self.error: Optional[str] = None

    # ---- 便捷方法: 在 orchestrator 执行过程中逐步记录 ----

    def begin(self, user_input: str, model: str = ""):
        """标记会话开始"""
        self.user_input = user_input
        self.model = model
        self.start_time = time.time()

    def record_intent(self, intent: dict):
        """记录意图识别结果"""
        self.intent = intent

    def record_tool_call(self, tool_name: str, args: dict, result: dict,
                         duration_ms: int = 0):
        """记录一次工具调用"""
        self.tool_calls.append({
            "tool": tool_name,
            "args": args,
            "result": result,
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration_ms,
        })

    def record_plan(self, plan_raw: str, plan_structured: dict = None):
        """记录最终的规划结果"""
        self.plan_raw = plan_raw
        self.plan_structured = plan_structured

    def finish(self, success: bool = True, error: str = None):
        """标记会话结束"""
        self.end_time = time.time()
        self.success = success
        self.error = error

    @property
    def duration_seconds(self) -> float:
        if self.end_time and self.start_time:
            return round(self.end_time - self.start_time, 2)
        return 0

    def to_meta_dict(self) -> dict:
        """导出元数据 (不含大体积数据)"""
        return {
            "session_id": self.session_id,
            "user_input": self.user_input,
            "model": self.model,
            "created_at": self.created_at,
            "duration_seconds": self.duration_seconds,
            "success": self.success,
            "error": self.error,
            "tool_call_count": len(self.tool_calls),
            "destination": self.intent.get("destination", "") if self.intent else "",
            "duration_days": self.intent.get("duration_days", 0) if self.intent else 0,
        }


class ResultStore:
    """
    结果存储管理器

    负责将 PlanningSession 持久化到磁盘,
    以及将历史结果导出为 TravelPlanner / TripTailor 评测格式.
    """

    def __init__(self, output_dir: str = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(__file__).parent / "outputs"

        # 子目录
        self.sessions_dir = self.output_dir / "sessions"
        self.exports_dir = self.output_dir / "exports"
        self.history_file = self.output_dir / "history.jsonl"

        # 确保目录存在
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    # ==============================================================
    # 保存会话
    # ==============================================================

    def save_session(self, session: PlanningSession) -> str:
        """
        持久化一次完整的规划会话

        Args:
            session: 已填充数据的会话对象

        Returns:
            会话目录路径
        """
        session_dir = self.sessions_dir / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # 1. meta.json
        self._write_json(session_dir / "meta.json", session.to_meta_dict())

        # 2. intent.json
        if session.intent:
            self._write_json(session_dir / "intent.json", {
                "user_input": session.user_input,
                "intent": session.intent,
            })

        # 3. tool_calls.json
        if session.tool_calls:
            self._write_json(session_dir / "tool_calls.json", {
                "count": len(session.tool_calls),
                "calls": session.tool_calls,
            })

        # 4. plan_raw.md
        if session.plan_raw:
            (session_dir / "plan_raw.md").write_text(
                session.plan_raw, encoding="utf-8"
            )

        # 5. plan_structured.json
        if session.plan_structured:
            self._write_json(session_dir / "plan_structured.json",
                             session.plan_structured)

        # 6. 追加到历史索引
        self._append_history(session)

        return str(session_dir)

    # ==============================================================
    # 加载会话
    # ==============================================================

    def load_session(self, session_id: str) -> Optional[PlanningSession]:
        """从磁盘加载一个会话"""
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            return None

        session = PlanningSession(session_id)

        # meta
        meta = self._read_json(session_dir / "meta.json")
        if meta:
            session.user_input = meta.get("user_input", "")
            session.model = meta.get("model", "")
            session.created_at = meta.get("created_at", "")
            session.success = meta.get("success", False)
            session.error = meta.get("error")

        # intent
        intent_data = self._read_json(session_dir / "intent.json")
        if intent_data:
            session.intent = intent_data.get("intent")

        # tool_calls
        tc_data = self._read_json(session_dir / "tool_calls.json")
        if tc_data:
            session.tool_calls = tc_data.get("calls", [])

        # plan_raw
        plan_raw_path = session_dir / "plan_raw.md"
        if plan_raw_path.exists():
            session.plan_raw = plan_raw_path.read_text(encoding="utf-8")

        # plan_structured
        session.plan_structured = self._read_json(
            session_dir / "plan_structured.json"
        )

        return session

    def list_sessions(self) -> list[dict]:
        """列出所有历史会话的元数据"""
        sessions = []
        if self.history_file.exists():
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            sessions.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        return sessions

    # ==============================================================
    # 导出为 TravelPlanner 评测格式
    # ==============================================================

    def export_travelplanner(self, session_ids: list[str] = None,
                             output_file: str = None) -> str:
        """
        导出为 TravelPlanner 评测 JSONL 格式

        TravelPlanner submission 格式 (每行一个JSON):
        {
            "idx": 1,
            "query": "用户查询",
            "plan": [
                {
                    "days": 1,
                    "current_city": "from A to B",
                    "transportation": "Flight Number: ...",
                    "breakfast": "餐厅名, 城市",
                    "attraction": "景点1, 城市;景点2, 城市",
                    "lunch": "餐厅名, 城市",
                    "dinner": "餐厅名, 城市",
                    "accommodation": "酒店名, 城市"
                }
            ]
        }
        """
        sessions = self._get_sessions(session_ids)
        if not sessions:
            print("  [WARN] No sessions to export")
            return ""

        export_dir = self.exports_dir / "travelplanner"
        export_dir.mkdir(parents=True, exist_ok=True)

        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = str(export_dir / f"submission_{timestamp}.jsonl")

        with open(output_file, "w", encoding="utf-8") as f:
            for idx, session in enumerate(sessions, 1):
                plan_json = self._convert_to_travelplanner_plan(session)
                submission = {
                    "idx": idx,
                    "query": session.user_input,
                    "plan": plan_json,
                }
                f.write(json.dumps(submission, ensure_ascii=False) + "\n")

        print(f"  [OK] TravelPlanner format exported: {output_file}")
        print(f"       Total: {len(sessions)} plans")
        return output_file

    def _convert_to_travelplanner_plan(self, session: PlanningSession) -> list:
        """
        将 plan_structured 转换为 TravelPlanner 评测的 plan 列表

        目标格式的每天:
        {
            "days": N,
            "current_city": "城市名 / from A to B",
            "transportation": "具体交通信息 / -",
            "breakfast": "餐厅名, 城市 / -",
            "attraction": "景点1, 城市;景点2, 城市 / -",
            "lunch": "餐厅名, 城市 / -",
            "dinner": "餐厅名, 城市 / -",
            "accommodation": "酒店名, 城市 / -"
        }
        """
        plan = session.plan_structured
        if not plan:
            return []

        dest = ""
        departure = ""
        if session.intent:
            dest = session.intent.get("destination", "")
            departure = session.intent.get("departure_city", "") or ""

        days_list = []
        itinerary = plan.get("itinerary", {})
        total_days = len(itinerary)

        for day_idx in range(1, total_days + 1):
            day_key = f"day_{day_idx}"
            activities = itinerary.get(day_key, [])

            # 分类活动
            sightseeings = []
            meals = {"breakfast": "-", "lunch": "-", "dinner": "-"}

            for act in activities:
                action = act.get("action", "")
                location = act.get("location", "")
                time_str = act.get("time", "")

                if action == "sightseeing":
                    sightseeings.append(f"{location}, {dest}" if dest else location)
                elif action == "dining":
                    # 根据时间判断是哪餐
                    meal_type = self._classify_meal_time(time_str)
                    loc_str = f"{location}, {dest}" if dest else location
                    meals[meal_type] = loc_str

            # 交通
            transportation = "-"
            if day_idx == 1 and plan.get("transportation"):
                trans = plan["transportation"][0]
                mode = trans.get("mode", "")
                number = trans.get("number", "")
                route = trans.get("route", "")
                trans_time = trans.get("time", "")
                if number:
                    transportation = f"{'Flight Number' if 'flight' in mode.lower() else 'Train Number'}: {number}, {route}, Departure Time: {trans_time}"
            elif day_idx == total_days and plan.get("transportation") and len(plan["transportation"]) >= 2:
                trans = plan["transportation"][-1]
                mode = trans.get("mode", "")
                number = trans.get("number", "")
                route = trans.get("route", "")
                trans_time = trans.get("time", "")
                if number:
                    transportation = f"{'Flight Number' if 'flight' in mode.lower() else 'Train Number'}: {number}, {route}, Departure Time: {trans_time}"

            # current_city
            if day_idx == 1 and departure and dest:
                current_city = f"from {departure} to {dest}"
            elif day_idx == total_days and departure and dest:
                current_city = f"from {dest} to {departure}"
            else:
                current_city = dest or "-"

            # accommodation
            accommodation = "-"
            if day_idx < total_days and plan.get("hotel"):
                hotel = plan["hotel"][0]
                hotel_name = hotel.get("name", "")
                accommodation = f"{hotel_name}, {dest}" if dest and hotel_name else hotel_name or "-"

            days_list.append({
                "days": day_idx,
                "current_city": current_city,
                "transportation": transportation,
                "breakfast": meals["breakfast"],
                "attraction": ";".join(sightseeings) + (";" if sightseeings else "") if sightseeings else "-",
                "lunch": meals["lunch"],
                "dinner": meals["dinner"],
                "accommodation": accommodation,
            })

        return days_list

    @staticmethod
    def _classify_meal_time(time_str: str) -> str:
        """根据时间字符串判断是哪一餐"""
        if not time_str:
            return "lunch"  # 默认
        # 尝试提取小时
        import re
        match = re.search(r"(\d{1,2})[:\s]", time_str)
        if match:
            hour = int(match.group(1))
            if hour < 10:
                return "breakfast"
            elif hour < 14:
                return "lunch"
            else:
                return "dinner"
        # 通过关键词判断
        lower = time_str.lower()
        if any(k in lower for k in ["早", "morning", "breakfast", "7:", "8:", "9:"]):
            return "breakfast"
        elif any(k in lower for k in ["晚", "evening", "dinner", "18:", "19:", "20:"]):
            return "dinner"
        return "lunch"

    # ==============================================================
    # 导出为 TripTailor 评测格式
    # ==============================================================

    def export_triptailor(self, session_ids: list[str] = None,
                          plan_key: str = "orchestrator_agent",
                          output_file: str = None) -> str:
        """
        导出为 TripTailor 评测 JSON 格式

        TripTailor result 格式 (JSON数组):
        [
            {
                "pid": "1",
                "query": "用户查询",
                "day": 3,
                "budget": 5000,
                "destination_city": "目的地",
                "<plan_key>_plan": "原始文本...",
                "<plan_key>_plan_json": "{\"hotel\": [...], ...}"
            }
        ]

        plan_json 内部格式:
        {
            "hotel": [{"day": 1, "name": "酒店", "price_per_night": 300}],
            "transportation": [
                {"day": 1, "mode": "Train", "route": "A to B", "number": "G123", "time": "08:00", "price": 200}
            ],
            "itinerary": {
                "day_1": [{"time": "09:00-11:00", "location": "景点名", "price": 50, "action": "sightseeing"}],
                "day_2": [...]
            }
        }
        """
        sessions = self._get_sessions(session_ids)
        if not sessions:
            print("  [WARN] No sessions to export")
            return ""

        export_dir = self.exports_dir / "triptailor"
        export_dir.mkdir(parents=True, exist_ok=True)

        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = str(export_dir / f"result_{timestamp}.json")

        results = []
        for idx, session in enumerate(sessions, 1):
            plan_structured = session.plan_structured or {}
            plan_json_str = json.dumps(plan_structured, ensure_ascii=False)

            item = {
                "pid": str(idx),
                "query": session.user_input,
                "day": session.intent.get("duration_days", 0) if session.intent else 0,
                "budget": session.intent.get("budget") if session.intent else None,
                "destination_city": session.intent.get("destination", "") if session.intent else "",
                f"{plan_key}_plan": session.plan_raw,
                f"{plan_key}_plan_json": plan_json_str,
            }
            results.append(item)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"  [OK] TripTailor format exported: {output_file}")
        print(f"       Total: {len(sessions)} plans, plan_key = '{plan_key}'")
        return output_file

    # ==============================================================
    # 内部工具方法
    # ==============================================================

    def _get_sessions(self, session_ids: list[str] = None) -> list[PlanningSession]:
        """获取指定的（或全部）会话"""
        if session_ids:
            sessions = []
            for sid in session_ids:
                s = self.load_session(sid)
                if s:
                    sessions.append(s)
            return sessions
        else:
            # 加载全部会话
            sessions = []
            if self.sessions_dir.exists():
                for d in sorted(self.sessions_dir.iterdir()):
                    if d.is_dir():
                        s = self.load_session(d.name)
                        if s:
                            sessions.append(s)
            return sessions

    def _append_history(self, session: PlanningSession):
        """追加会话索引到 history.jsonl"""
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(session.to_meta_dict(), ensure_ascii=False) + "\n")

    @staticmethod
    def _write_json(path: Path, data: dict):
        """写入 JSON 文件"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _read_json(path: Path) -> Optional[dict]:
        """读取 JSON 文件"""
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

