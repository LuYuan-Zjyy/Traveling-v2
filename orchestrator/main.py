#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
主控Agent 启动入口

使用方法:
    # 交互模式 (推荐)
    python -m orchestrator.main

    # 单次查询
    python -m orchestrator.main --query "我想去安庆玩3天，体验黄梅戏和乡村文化"

    # 指定API Key (也可通过 .env 配置)
    python -m orchestrator.main --deepseek-key sk-xxx --amap-key xxx

    # 查看历史会话
    python -m orchestrator.main --history

    # 导出评测数据
    python -m orchestrator.export_eval --format triptailor
    python -m orchestrator.export_eval --format travelplanner
"""

import sys
import argparse
from orchestrator.config import load_config, AgentConfig, DeepSeekConfig, AmapConfig
from orchestrator.orchestrator import TravelOrchestrator
from orchestrator.result_store import ResultStore


def parse_args():
    parser = argparse.ArgumentParser(
        description="Travel Orchestrator Agent (DeepSeek + Gaode MCP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m orchestrator.main
  python -m orchestrator.main --query "春节去安庆3天，预算5000"
  python -m orchestrator.main --deepseek-key sk-xxx --amap-key xxx
  python -m orchestrator.main --history

评测导出:
  python -m orchestrator.export_eval --list
  python -m orchestrator.export_eval --format triptailor
  python -m orchestrator.export_eval --format travelplanner

需要配置的Key:
  DEEPSEEK_API_KEY  - DeepSeek API密钥 (https://platform.deepseek.com)
  AMAP_API_KEY      - 高德地图Web服务Key (https://console.amap.com)
        """,
    )
    parser.add_argument("--query", "-q", type=str, default=None,
                        help="旅行需求 (不填则进入交互模式)")
    parser.add_argument("--deepseek-key", type=str, default=None,
                        help="DeepSeek API Key")
    parser.add_argument("--deepseek-model", type=str, default=None,
                        help="DeepSeek模型名 (默认: deepseek-chat)")
    parser.add_argument("--amap-key", type=str, default=None,
                        help="高德地图API Key")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="输出文件路径 (不填则打印到终端)")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="数据存储根目录 (默认: orchestrator/outputs)")
    parser.add_argument("--history", action="store_true",
                        help="查看历史规划会话")
    return parser.parse_args()


def build_config(args) -> AgentConfig:
    """从命令行参数和环境变量构建配置"""
    overrides = {}
    if args.deepseek_key:
        overrides["deepseek_api_key"] = args.deepseek_key
    if args.deepseek_model:
        overrides["deepseek_model"] = args.deepseek_model
    if args.amap_key:
        overrides["amap_api_key"] = args.amap_key
    return load_config(**overrides)


def show_history(store: ResultStore):
    """显示历史会话列表"""
    sessions = store.list_sessions()
    if not sessions:
        print("\n  [INFO] No sessions yet.")
        print("  Run: python -m orchestrator.main --query '...' to create your first plan\n")
        return

    print(f"\n  [HISTORY] {len(sessions)} sessions:")
    print("  " + "-" * 72)
    print(f"  {'#':>3}  {'会话ID':<26}  {'目的地':<8}  {'天数':>4}  {'耗时':>6}  {'状态':<4}")
    print("  " + "-" * 72)

    for i, meta in enumerate(sessions, 1):
        sid = meta.get("session_id", "?")
        dest = meta.get("destination", "?")[:6]
        days = meta.get("duration_days", "?")
        dur = meta.get("duration_seconds", 0)
        ok = "OK" if meta.get("success") else "FAIL"
        tools = meta.get("tool_call_count", 0)
        print(f"  {i:>3}  {sid:<26}  {dest:<8}  {days:>4}  {dur:>5.1f}s  {ok}  (工具×{tools})")

    print("  " + "-" * 72)
    print(f"\n  [TIP] Export for evaluation:")
    print(f"     python -m orchestrator.export_eval --format triptailor")
    print(f"     python -m orchestrator.export_eval --format travelplanner")
    print(f"     python -m orchestrator.export_eval --detail <session_id>\n")


def run_single_query(agent: TravelOrchestrator, query: str, output_path: str = None):
    """执行单次查询"""
    plan = agent.plan(query)

    print("\n" + "=" * 60)
    print("  Travel Plan")
    print("=" * 60 + "\n")
    print(plan)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(plan)
        print(f"\n  [SAVE] Plan saved to: {output_path}")

    session = agent.last_session
    if session and session.plan_structured:
        itinerary = session.plan_structured.get("itinerary", {})
        print(f"\n  [OK] Structured data: {len(itinerary)} days")
        print(f"       Session: {session.session_id}")
        print(f"       Path: orchestrator/outputs/sessions/{session.session_id}/")
    elif session:
        print(f"\n  [WARN] No structured data (Markdown plan saved)")
        print(f"       Session: {session.session_id}")


def run_interactive(agent: TravelOrchestrator):
    """交互模式"""
    print("\n" + "=" * 60)
    print("  Travel Orchestrator Agent - Interactive Mode")
    print("  Type your travel request, 'quit' to exit")
    print("  'history' to view past sessions, 'export' to export data")
    print("=" * 60)

    while True:
        try:
            print()
            user_input = input("> Your travel request: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break
        if user_input.lower() in ("history",):
            show_history(agent.store)
            continue
        if user_input.lower() in ("export",):
            print("  [TIP] Use export commands:")
            print("     python -m orchestrator.export_eval --format triptailor")
            print("     python -m orchestrator.export_eval --format travelplanner")
            continue

        try:
            plan = agent.plan(user_input)
            print("\n" + "=" * 60)
            print("  Travel Plan")
            print("=" * 60 + "\n")
            print(plan)

            session = agent.last_session
            if session:
                print(f"\n  [SAVE] Session: {session.session_id}")
                if session.plan_structured:
                    days = len(session.plan_structured.get("itinerary", {}))
                    print(f"  [OK] Structured: {days} days (export-ready)")
                else:
                    print(f"  [WARN] No structured data")

        except Exception as e:
            print(f"\n  [ERROR] Planning failed: {e}")
            import traceback
            traceback.print_exc()


def main():
    args = parse_args()

    # 初始化存储
    store = ResultStore(output_dir=args.output_dir)

    # 查看历史
    if args.history:
        show_history(store)
        return

    # 构建配置
    config = build_config(args)

    # 校验Key
    missing = config.validate()
    if missing:
        print(f"\n  [ERROR] Missing API Key: {', '.join(missing)}")
        print(f"\n配置方式 (任选其一):")
        print(f"  1. 在项目根目录创建 .env 文件 (参考 env.example)")
        print(f"  2. 设置环境变量: export DEEPSEEK_API_KEY=xxx")
        print(f"  3. 命令行参数: --deepseek-key xxx --amap-key xxx")
        sys.exit(1)

    # 创建Agent (注入存储)
    agent = TravelOrchestrator(config, store=store)

    # 执行
    if args.query:
        run_single_query(agent, args.query, args.output)
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
