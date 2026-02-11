#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
评测数据导出工具

将 orchestrator 存储的规划结果导出为 TravelPlanner / TripTailor 评测框架
所需要的格式，从而可以直接调用评测脚本打分。

使用方法:
    # 查看所有历史会话
    python -m orchestrator.export_eval --list

    # 导出全部会话为 TripTailor 评测格式
    python -m orchestrator.export_eval --format triptailor

    # 导出全部会话为 TravelPlanner 评测格式
    python -m orchestrator.export_eval --format travelplanner

    # 导出指定会话
    python -m orchestrator.export_eval --format triptailor --sessions 20260210_143000_123456

    # 导出后直接运行评测
    python -m orchestrator.export_eval --format triptailor --run-eval

导出格式说明:

  TravelPlanner (JSONL):
    每行 {"idx": N, "query": "...", "plan": [{days, current_city, ...}]}
    → 可直接传给 TravelPlanner/run_eval_pipeline.py --skip_generation --input_file

  TripTailor (JSON):
    [{"pid": "N", "query": "...", "<plan_key>_plan": "...", "<plan_key>_plan_json": "..."}]
    → 可直接传给 TripTailor/TripTailor/run_eval_pipeline.py --skip_generation --input_file
"""

import os
import sys
import json
import argparse
from datetime import datetime

from orchestrator.result_store import ResultStore


def list_sessions(store: ResultStore):
    """列出所有历史会话"""
    sessions = store.list_sessions()
    if not sessions:
        print("\n  [INFO] No sessions yet.")
        print("  请先运行: python -m orchestrator.main --query '你的旅行需求'")
        return

    print(f"\n  [LIST] {len(sessions)} sessions:")
    print("  " + "-" * 70)
    print(f"  {'#':>3}  {'会话ID':<26}  {'目的地':<8}  {'天数':>4}  {'耗时':>6}  {'状态':<4}")
    print("  " + "-" * 70)

    for i, meta in enumerate(sessions, 1):
        sid = meta.get("session_id", "?")
        dest = meta.get("destination", "?")[:6]
        days = meta.get("duration_days", "?")
        dur = meta.get("duration_seconds", 0)
        ok = "OK" if meta.get("success") else "FAIL"
        tools = meta.get("tool_call_count", 0)

        print(f"  {i:>3}  {sid:<26}  {dest:<8}  {days:>4}  {dur:>5.1f}s  {ok}  (工具×{tools})")

    print("  " + "-" * 70)
    print(f"\n  [TIP] Export commands:")
    print(f"     python -m orchestrator.export_eval --format triptailor")
    print(f"     python -m orchestrator.export_eval --format travelplanner")


def show_session_detail(store: ResultStore, session_id: str):
    """显示单个会话详情"""
    session = store.load_session(session_id)
    if not session:
        print(f"\n  [ERROR] Session not found: {session_id}")
        return

    print(f"\n  [DETAIL] Session: {session_id}")
    print("  " + "=" * 60)
    print(f"  用户输入: {session.user_input}")
    print(f"  模型:     {session.model}")
    print(f"  创建时间: {session.created_at}")
    print(f"  Status:   {'OK' if session.success else 'FAIL'}")
    if session.error:
        print(f"  错误:     {session.error}")

    if session.intent:
        print(f"\n  --- 意图识别 ---")
        print(f"  目的地: {session.intent.get('destination', '?')}")
        print(f"  天数:   {session.intent.get('duration_days', '?')}")
        print(f"  预算:   {session.intent.get('budget', '?')}")
        print(f"  偏好:   {session.intent.get('preferences', [])}")

    if session.tool_calls:
        print(f"\n  --- 工具调用 ({len(session.tool_calls)}次) ---")
        for i, tc in enumerate(session.tool_calls, 1):
            args_str = json.dumps(tc["args"], ensure_ascii=False)
            if len(args_str) > 60:
                args_str = args_str[:60] + "..."
            has_error = "error" in tc.get("result", {})
            status = "WARN" if has_error else "OK"
            ms = tc.get("duration_ms", 0)
            print(f"  {i:>3}. {status} {tc['tool']}({args_str}) [{ms}ms]")

    if session.plan_structured:
        plan = session.plan_structured
        hotel_count = len(plan.get("hotel", []))
        trans_count = len(plan.get("transportation", []))
        day_count = len(plan.get("itinerary", {}))
        print(f"\n  --- 结构化规划 ---")
        print(f"  行程天数: {day_count}")
        print(f"  酒店:     {hotel_count} 条")
        print(f"  交通:     {trans_count} 条")
        for day_key in sorted(plan.get("itinerary", {}).keys()):
            acts = plan["itinerary"][day_key]
            sights = sum(1 for a in acts if a.get("action") == "sightseeing")
            meals = sum(1 for a in acts if a.get("action") == "dining")
            print(f"    {day_key}: {sights} 景点, {meals} 餐")
    elif session.plan_raw:
        print(f"\n  --- 原始规划 (前200字) ---")
        print(f"  {session.plan_raw[:200]}...")

    print("  " + "=" * 60)


def run_triptailor_eval(export_file: str):
    """调用 TripTailor 评测脚本"""
    triptailor_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "TripTailor", "TripTailor"
    )
    eval_script = os.path.join(triptailor_dir, "run_eval_pipeline.py")

    if not os.path.exists(eval_script):
        print(f"  [WARN] TripTailor eval script not found: {eval_script}")
        return

    print(f"\n  [EVAL] Running TripTailor evaluation...")
    print(f"     脚本: {eval_script}")
    print(f"     输入: {export_file}")

    cmd = (
        f'python "{eval_script}" '
        f'--skip_generation '
        f'--input_file "{export_file}"'
    )
    print(f"     命令: {cmd}\n")
    os.system(cmd)


def run_travelplanner_eval(export_file: str):
    """调用 TravelPlanner 评测脚本 (standalone 模式, 不依赖 HuggingFace/沙盒)"""
    tp_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "TravelPlanner"
    )
    eval_script = os.path.join(tp_dir, "run_eval_pipeline.py")

    if not os.path.exists(eval_script):
        print(f"  [WARN] TravelPlanner eval script not found: {eval_script}")
        return

    print(f"\n  Running TravelPlanner evaluation (standalone)...")
    print(f"     Script: {eval_script}")
    print(f"     Input:  {export_file}")

    cmd = (
        f'python "{eval_script}" '
        f'--skip_generation '
        f'--standalone '
        f'--input_file "{export_file}"'
    )
    print(f"     Command: {cmd}\n")
    os.system(cmd)


def main():
    parser = argparse.ArgumentParser(
        description="Export Agent results for TripTailor/TravelPlanner evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--list", "-l", action="store_true",
                        help="列出所有历史会话")
    parser.add_argument("--detail", type=str, default="",
                        help="查看指定会话的详细信息")
    parser.add_argument("--format", "-f", type=str,
                        choices=["travelplanner", "triptailor", "both"],
                        help="导出格式: travelplanner / triptailor / both")
    parser.add_argument("--sessions", "-s", type=str, nargs="*", default=None,
                        help="导出指定会话ID (空=全部)")
    parser.add_argument("--plan-key", type=str, default="orchestrator_agent",
                        help="TripTailor plan_key (默认: orchestrator_agent)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="输出文件路径 (默认自动生成)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="输出根目录 (默认: orchestrator/outputs)")
    parser.add_argument("--run-eval", action="store_true",
                        help="导出后直接运行评测脚本")

    args = parser.parse_args()
    store = ResultStore(output_dir=args.output_dir)

    if args.list:
        list_sessions(store)
        return

    if args.detail:
        show_session_detail(store, args.detail)
        return

    if not args.format:
        parser.print_help()
        print("\n  [TIP] Common commands:")
        print("     --list                      查看历史会话")
        print("     --format triptailor          导出为 TripTailor 格式")
        print("     --format travelplanner       导出为 TravelPlanner 格式")
        print("     --format both                同时导出两种格式")
        print("     --detail <session_id>        查看会话详情")
        return

    # 导出
    session_ids = args.sessions
    export_files = {}

    if args.format in ("triptailor", "both"):
        f = store.export_triptailor(
            session_ids=session_ids,
            plan_key=args.plan_key,
            output_file=args.output if args.format == "triptailor" else None,
        )
        if f:
            export_files["triptailor"] = f

    if args.format in ("travelplanner", "both"):
        f = store.export_travelplanner(
            session_ids=session_ids,
            output_file=args.output if args.format == "travelplanner" else None,
        )
        if f:
            export_files["travelplanner"] = f

    # 汇总
    if export_files:
        print(f"\n  [OK] Export complete:")
        for fmt, path in export_files.items():
            print(f"     {fmt}: {path}")

    # 可选: 直接运行评测
    if args.run_eval and export_files:
        if "triptailor" in export_files:
            run_triptailor_eval(export_files["triptailor"])
        if "travelplanner" in export_files:
            run_travelplanner_eval(export_files["travelplanner"])


if __name__ == "__main__":
    main()

