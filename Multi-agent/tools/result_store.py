"""
结果存储模块 (Result Store)

系统性地存储 Agent 的每一次规划过程和结果
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


class PlanningSession:
    """单次规划会话的数据容器"""

    def __init__(self, session_id: str = None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.created_at = datetime.now().isoformat()

        self.user_input: str = ""
        self.intent: Optional[dict] = None
        self.tool_calls: list = []
        self.plan_raw: str = ""
        self.plan_structured: Optional[dict] = None

        self.model: str = ""
        self.start_time: float = 0
        self.end_time: float = 0
        self.success: bool = False
        self.error: Optional[str] = None

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
        """导出元数据"""
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
    """结果存储管理器"""

    def __init__(self, output_dir: str = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(__file__).parent.parent / "outputs"

        self.sessions_dir = self.output_dir / "sessions"
        self.exports_dir = self.output_dir / "exports"
        self.history_file = self.output_dir / "history.jsonl"

        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    def save_session(self, session: PlanningSession) -> str:
        """持久化一次完整的规划会话"""
        session_dir = self.sessions_dir / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        self._write_json(session_dir / "meta.json", session.to_meta_dict())

        if session.intent:
            self._write_json(session_dir / "intent.json", {
                "user_input": session.user_input,
                "intent": session.intent,
            })

        if session.tool_calls:
            self._write_json(session_dir / "tool_calls.json", {
                "count": len(session.tool_calls),
                "calls": session.tool_calls,
            })

        if session.plan_raw:
            (session_dir / "plan_raw.md").write_text(
                session.plan_raw, encoding="utf-8"
            )

        if session.plan_structured:
            self._write_json(session_dir / "plan_structured.json",
                             session.plan_structured)

        self._append_history(session)

        return str(session_dir)

    def load_session(self, session_id: str) -> Optional[PlanningSession]:
        """从磁盘加载一个会话"""
        session_dir = self.sessions_dir / session_id
        if not session_dir.exists():
            return None

        session = PlanningSession(session_id)

        meta = self._read_json(session_dir / "meta.json")
        if meta:
            session.user_input = meta.get("user_input", "")
            session.model = meta.get("model", "")
            session.created_at = meta.get("created_at", "")
            session.success = meta.get("success", False)
            session.error = meta.get("error")

        intent_data = self._read_json(session_dir / "intent.json")
        if intent_data:
            session.intent = intent_data.get("intent")

        tc_data = self._read_json(session_dir / "tool_calls.json")
        if tc_data:
            session.tool_calls = tc_data.get("calls", [])

        plan_raw_path = session_dir / "plan_raw.md"
        if plan_raw_path.exists():
            session.plan_raw = plan_raw_path.read_text(encoding="utf-8")

        session.plan_structured = self._read_json(
            session_dir / "plan_structured.json"
        )

        return session

    def list_sessions(self) -> list:
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
