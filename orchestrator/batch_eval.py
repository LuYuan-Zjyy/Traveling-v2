#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Orchestrator Agent 评测脚本

用 TripTailor/data/test.json 作为测试集,
调用 Orchestrator Agent (DeepSeek + 高德MCP) 生成旅行规划,
然后用 TripTailor StrictEvaluator 打分.

评测目的: 验证接入高德MCP后的 Agent 在标准测试集上的表现.

流程:
  1. 读取 TripTailor/data/test.json (703条标准测试样本)
  2. 逐条调用 Orchestrator Agent 生成规划
  3. Agent 输出结构化 JSON (hotel/transportation/itinerary)
  4. 用 TripTailor StrictEvaluator 打分
  5. 输出评测报告

使用方法:
    # 跑前3条测试 (推荐先小规模验证)
    python -m orchestrator.batch_eval --max 3

    # 跑前20条
    python -m orchestrator.batch_eval --max 20

    # 跑全部703条 (耗时较长)
    python -m orchestrator.batch_eval

    # 只评测已有结果文件 (跳过生成)
    python -m orchestrator.batch_eval --eval-only --input results.json

    # 指定输出目录
    python -m orchestrator.batch_eval --max 5 --output-dir ./my_eval
"""

import os
import sys
import json
import time
import argparse
import traceback
from datetime import datetime
from pathlib import Path


# ============================================================
# 工具函数
# ============================================================

def safe_print(msg: str):
    """Windows GBK 安全打印"""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', errors='replace').decode('ascii'))


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}min"
    else:
        return f"{seconds/3600:.1f}h"


def find_test_json() -> str:
    """自动定位 TripTailor/data/test.json"""
    project_root = Path(__file__).parent.parent
    candidates = [
        project_root / "TripTailor" / "data" / "test.json",
        Path("TripTailor") / "data" / "test.json",
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return ""


def find_info_json() -> str:
    """自动定位 TripTailor/data/infomation.json (评测沙盒数据)"""
    project_root = Path(__file__).parent.parent
    candidates = [
        project_root / "TripTailor" / "data" / "infomation.json",
        Path("TripTailor") / "data" / "infomation.json",
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return ""


# ============================================================
# Phase 1: 读取 TripTailor 测试集
# ============================================================

def load_test_data(test_file: str, max_samples: int = -1) -> list[dict]:
    """
    读取 TripTailor test.json

    每条样本包含:
      pid, query, destination_city, departure_city, day, budget,
      meal_price_range, final_plan (参考方案), final_plan_json (参考JSON)
    """
    safe_print(f"  Loading test data: {test_file}")
    with open(test_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if max_samples > 0:
        data = data[:max_samples]

    safe_print(f"  Loaded {len(data)} samples (total in file: queried {max_samples if max_samples > 0 else 'all'})")
    return data


# ============================================================
# Phase 2: 批量调用 Orchestrator Agent 生成规划
# ============================================================

def run_agent_generation(test_data: list[dict],
                         plan_key: str = "orchestrator_agent",
                         output_dir: str = None,
                         delay: float = 3.0,
                         retry: int = 2,
                         resume_file: str = None,
                         cooldown: float = 60.0,
                         max_consecutive_fails: int = 3) -> list[dict]:
    """
    对每条测试样本调用 Orchestrator Agent 生成规划,
    将结果直接写入样本的 {plan_key}_plan_json 字段.

    Args:
        resume_file: 已有进度文件路径, 自动跳过已完成的条目
        cooldown: 连续失败后的冷却等待时间(秒)
        max_consecutive_fails: 触发冷却的连续失败次数阈值

    Returns:
        list[dict]: 带有 agent 生成结果的测试数据
    """
    from orchestrator.config import load_config
    from orchestrator.orchestrator import TravelOrchestrator
    from orchestrator.result_store import ResultStore

    # 初始化 Agent
    config = load_config()
    missing = config.validate()
    if missing:
        safe_print(f"\n  [ERROR] Missing API Keys: {', '.join(missing)}")
        safe_print(f"  Configure in .env file:")
        safe_print(f"    DEEPSEEK_API_KEY=sk-xxx")
        safe_print(f"    AMAP_API_KEY=xxx")
        sys.exit(1)

    store = ResultStore(output_dir=output_dir)
    agent = TravelOrchestrator(config, store=store)

    total = len(test_data)
    results = []
    success_count = 0
    fail_count = 0
    skip_count = 0
    consecutive_fails = 0
    current_delay = delay          # 当前延迟 (自适应调整)
    total_start = time.time()

    # 中间结果文件 (每条都保存, 支持断点续传)
    progress_file = os.path.join(str(store.output_dir), f"{plan_key}_progress.json")

    # 加载已有进度 (断点续传)
    completed_map = {}
    if resume_file:
        # 优先用指定的文件, 否则用默认进度文件
        rf = resume_file if os.path.exists(resume_file) else progress_file
        completed_map = _load_resume_data(rf, plan_key)
        if completed_map:
            safe_print(f"\n  [RESUME] 已加载 {len(completed_map)} 条已完成结果")
            safe_print(f"           来源: {rf}")

    safe_print(f"\n{'='*65}")
    safe_print(f"  Orchestrator Agent Generation")
    safe_print(f"  Samples: {total} | Delay: {delay}s | Retry: {retry}")
    if completed_map:
        safe_print(f"  Resume: {len(completed_map)} already done, ~{total - len(completed_map)} remaining")
    safe_print(f"  Cooldown: {cooldown}s after {max_consecutive_fails} consecutive failures")
    safe_print(f"  Plan Key: {plan_key}")
    safe_print(f"{'='*65}")

    for i, item in enumerate(test_data):
        pid = item.get("pid", i + 1)
        query = item.get("query", "")
        dest = item.get("destination_city", "?")

        # ---- 断点续传: 跳过已完成的条目 ----
        if pid in completed_map:
            skip_count += 1
            results.append(completed_map[pid])
            success_count += 1
            if skip_count <= 5 or skip_count % 50 == 0:
                safe_print(f"  [SKIP] PID={pid} | {dest} (already done)")
            continue

        safe_print(f"\n{'~'*65}")
        safe_print(f"  [{i+1}/{total}] PID={pid} | {dest} | {query[:55]}...")
        safe_print(f"{'~'*65}")

        result_item = item.copy()  # 保留原始字段 (pid, budget, day, etc.)
        item_success = False

        for attempt in range(1, retry + 1):
            t0 = time.time()
            try:
                # 调用 Orchestrator Agent
                plan_text = agent.plan(query)
                duration = time.time() - t0

                # 获取结构化结果
                session = agent.last_session
                plan_structured = session.plan_structured if session else None

                if plan_structured:
                    # 写入 TripTailor 评测格式的字段
                    result_item[f"{plan_key}_plan"] = plan_text
                    result_item[f"{plan_key}_plan_json"] = json.dumps(
                        plan_structured, ensure_ascii=False
                    )
                    success_count += 1
                    item_success = True
                    safe_print(f"  [OK] PID={pid} done in {format_duration(duration)}")
                    days = len(plan_structured.get("itinerary", {}))
                    safe_print(f"       Structured: {days} days itinerary")
                else:
                    # 有文本但没有结构化数据
                    result_item[f"{plan_key}_plan"] = plan_text
                    result_item[f"{plan_key}_plan_json"] = "{}"
                    success_count += 1
                    item_success = True
                    safe_print(f"  [WARN] PID={pid} done but no structured data ({format_duration(duration)})")
                break

            except KeyboardInterrupt:
                safe_print(f"\n  [ABORT] User interrupted. Saving progress...")
                results.append(result_item)
                _save_progress(results, progress_file, plan_key)
                raise

            except Exception as e:
                duration = time.time() - t0
                err_msg = str(e)
                if attempt < retry:
                    wait = delay * attempt
                    safe_print(f"  [RETRY] Attempt {attempt}/{retry} failed: {err_msg[:80]}")
                    safe_print(f"          Waiting {wait}s...")
                    time.sleep(wait)
                else:
                    fail_count += 1
                    result_item[f"{plan_key}_plan"] = ""
                    result_item[f"{plan_key}_plan_json"] = "{}"
                    safe_print(f"  [FAIL] PID={pid} all {retry} attempts failed: {err_msg[:100]}")

        # ---- 自适应延迟: 根据连续失败情况调整 ----
        if item_success:
            consecutive_fails = 0
            current_delay = delay  # 恢复正常延迟
        else:
            consecutive_fails += 1
            # 连续失败达到阈值 → 长时间冷却
            if consecutive_fails >= max_consecutive_fails:
                safe_print(f"\n  [COOLDOWN] {consecutive_fails} consecutive failures detected!")
                safe_print(f"             Cooling down for {cooldown}s to let API recover...")
                safe_print(f"             (Press Ctrl+C to abort and save progress)")
                try:
                    time.sleep(cooldown)
                except KeyboardInterrupt:
                    safe_print(f"\n  [ABORT] User interrupted during cooldown. Saving...")
                    results.append(result_item)
                    _save_progress(results, progress_file, plan_key)
                    raise
                consecutive_fails = 0  # 冷却后重置
                current_delay = delay * 2  # 冷却后用加倍延迟
                safe_print(f"             Cooldown done. Resuming with {current_delay}s delay...")
            else:
                # 每次失败逐步增加延迟
                current_delay = min(delay * (2 ** consecutive_fails), cooldown)
                safe_print(f"  [ADAPT] Delay increased to {current_delay:.0f}s "
                           f"(consecutive fails: {consecutive_fails})")

        results.append(result_item)

        # 实时保存进度
        _save_progress(results, progress_file, plan_key)

        # 进度统计
        done_count = success_count + fail_count
        elapsed = time.time() - total_start
        remaining = (elapsed / max(done_count, 1)) * (total - len(completed_map) - done_count + skip_count) if done_count > 0 else 0
        safe_print(f"  Progress: {i+1}/{total} | OK: {success_count} | Fail: {fail_count} | "
                   f"Skip: {skip_count} | ETA: {format_duration(remaining)}")

        # 限流等待 (使用自适应延迟)
        if i < total - 1:
            time.sleep(current_delay)

    total_elapsed = time.time() - total_start
    safe_print(f"\n{'='*65}")
    safe_print(f"  Generation Complete")
    safe_print(f"  Total: {total} | Success: {success_count} | Failed: {fail_count} | Skipped(resume): {skip_count}")
    safe_print(f"  Time: {format_duration(total_elapsed)}")
    safe_print(f"{'='*65}")

    return results


def _save_progress(results: list[dict], filepath: str, plan_key: str):
    """保存中间结果 (支持断点续传)"""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def _load_resume_data(filepath: str, plan_key: str) -> dict[int, dict]:
    """
    加载已有进度数据, 返回 {pid: result_item} 映射.
    只保留成功生成了 plan_json 的条目.
    """
    if not filepath or not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        completed = {}
        for item in data:
            pid = item.get("pid")
            plan_json = item.get(f"{plan_key}_plan_json", "{}")
            if pid is not None and plan_json and plan_json != "{}":
                completed[pid] = item
        return completed
    except Exception as e:
        safe_print(f"  [WARN] 无法加载续传文件: {e}")
        return {}


# ============================================================
# Phase 3: 运行 TripTailor 评测
# ============================================================

def run_triptailor_eval(results: list[dict], plan_key: str,
                        info_file: str = None,
                        output_dir: str = None) -> dict:
    """
    直接调用 TripTailor StrictEvaluator 对结果打分.

    不需要 subprocess, 直接 import 评测模块.
    """
    # 添加 TripTailor 到 path
    project_root = Path(__file__).parent.parent
    triptailor_dir = project_root / "TripTailor" / "TripTailor"

    if str(triptailor_dir) not in sys.path:
        sys.path.insert(0, str(triptailor_dir))

    try:
        from eval.simple_eval import StrictEvaluator, print_results
    except ImportError as e:
        safe_print(f"  [ERROR] Cannot import TripTailor evaluator: {e}")
        safe_print(f"  Make sure TripTailor/TripTailor/eval/simple_eval.py exists")
        safe_print(f"  And install deps: pip install pandas fuzzywuzzy geopy tqdm")
        return {}

    # 自动查找 info_file
    if not info_file:
        info_file = find_info_json()

    safe_print(f"\n{'='*65}")
    safe_print(f"  TripTailor Evaluation")
    safe_print(f"  Samples: {len(results)}")
    safe_print(f"  Plan Key: {plan_key}")
    safe_print(f"  Info File: {info_file or 'NOT FOUND'}")
    safe_print(f"{'='*65}")

    # 初始化评测器
    evaluator = StrictEvaluator(
        info_file=info_file if info_file and os.path.exists(info_file) else None
    )

    # 运行评测
    safe_print(f"\n  Running evaluation...")
    summary = evaluator.evaluate_batch(results, plan_key)

    # 打印结果
    print_results(summary, plan_key)

    # 保存评测结果
    if output_dir:
        eval_output = os.path.join(output_dir, f"{plan_key}_eval_result.json")
    else:
        eval_output = os.path.join(
            str(Path(__file__).parent / "outputs"),
            f"{plan_key}_eval_result.json"
        )
    os.makedirs(os.path.dirname(eval_output), exist_ok=True)

    eval_data = {
        "plan_key": plan_key,
        "total_score": summary.get("total_score", 0),
        "total_samples": summary.get("total_samples", 0),
        "metrics": summary.get("metrics", {}),
        "timestamp": datetime.now().isoformat(),
    }
    with open(eval_output, "w", encoding="utf-8") as f:
        json.dump(eval_data, f, ensure_ascii=False, indent=2)

    safe_print(f"\n  [SAVE] Eval result: {eval_output}")

    return summary


# ============================================================
# Phase 4: 汇总报告
# ============================================================

def print_summary(results: list[dict], summary: dict, plan_key: str):
    """打印最终汇总"""
    total = len(results)
    has_plan = sum(1 for r in results if r.get(f"{plan_key}_plan_json", "{}") != "{}")

    safe_print(f"\n{'='*65}")
    safe_print(f"  === FINAL SUMMARY ===")
    safe_print(f"{'='*65}")
    safe_print(f"  Test Samples:     {total}")
    safe_print(f"  Plans Generated:  {has_plan} ({has_plan/total*100:.1f}%)")
    safe_print(f"  Plans Failed:     {total - has_plan}")

    if summary and "total_score" in summary:
        safe_print(f"\n  TripTailor Score: {summary['total_score']:.2f} / 100")
        m = summary.get("metrics", {})
        safe_print(f"  ---")
        safe_print(f"  Completeness:     {m.get('completeness', 0):.1f}%")
        safe_print(f"  Within Sandbox:   {m.get('within_sandbox', 0):.1f}%")
        safe_print(f"  Diverse Attr:     {m.get('diverse_attractions', 0):.1f}%")
        safe_print(f"  Diverse Rest:     {m.get('diverse_restaurants', 0):.1f}%")
        safe_print(f"  Within Budget:    {m.get('within_budget', 0):.1f}%")
        safe_print(f"  Meal Prices:      {m.get('reasonable_meal_prices', 0):.1f}%")
        safe_print(f"  Duration:         {m.get('appropriate_duration', 0):.1f}%")
        safe_print(f"  Feasibility:      {m.get('feasibility', 0):.1f}%")
        safe_print(f"  Rationality:      {m.get('rationality', 0):.1f}%")

        # 沙盒详细
        safe_print(f"\n  Sandbox Detail:")
        safe_print(f"    Hotel:          {m.get('sandbox_hotel', 0):.1f}%")
        safe_print(f"    Transport:      {m.get('sandbox_transport', 0):.1f}%")
        safe_print(f"    Attraction:     {m.get('sandbox_attraction', 0):.1f}%")
        safe_print(f"    Restaurant:     {m.get('sandbox_restaurant', 0):.1f}%")

    safe_print(f"\n  Note: Sandbox metrics measure match against TripTailor's")
    safe_print(f"  internal database. Our agent uses real Gaode MCP data,")
    safe_print(f"  so sandbox scores reflect real-vs-sandbox gap.")
    safe_print(f"  Key metrics: Completeness, Diversity, Budget, Meal Prices.")
    safe_print(f"{'='*65}\n")


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Orchestrator Agent (DeepSeek+Gaode MCP) Evaluation with TripTailor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test with 3 samples
  python -m orchestrator.batch_eval --max 3

  # Run samples 1-100 (batch 1)
  python -m orchestrator.batch_eval --start 1 --end 100

  # Run samples 101-200 (batch 2)
  python -m orchestrator.batch_eval --start 101 --end 200

  # Resume from last run (auto-skip completed items)
  python -m orchestrator.batch_eval --max 200 --resume

  # Resume with custom cooldown (120s pause after 5 consecutive fails)
  python -m orchestrator.batch_eval --resume --cooldown 120 --max-consecutive-fails 5

  # Evaluate existing result file (skip generation)
  python -m orchestrator.batch_eval --eval-only --input results.json

  # Full 703 samples (takes hours)
  python -m orchestrator.batch_eval
        """,
    )

    parser.add_argument("--max", "-n", type=int, default=-1,
                        help="Max samples to test (-1 = all 703)")
    parser.add_argument("--delay", type=float, default=3.0,
                        help="Delay between API calls in seconds (default: 3)")
    parser.add_argument("--retry", type=int, default=2,
                        help="Max retries per sample (default: 2)")
    parser.add_argument("--plan-key", type=str, default="orchestrator_agent",
                        help="Plan key for evaluation (default: orchestrator_agent)")

    # 断点续传 & 分批控制
    parser.add_argument("--resume", action="store_true",
                        help="Resume from progress file, skip already completed items")
    parser.add_argument("--resume-file", type=str, default=None,
                        help="Specific progress file to resume from (auto-detected if not set)")
    parser.add_argument("--start", type=int, default=1,
                        help="Start index in test set (1-based, default: 1)")
    parser.add_argument("--end", type=int, default=-1,
                        help="End index in test set (1-based inclusive, -1 = all)")

    # 连续失败冷却
    parser.add_argument("--cooldown", type=float, default=60.0,
                        help="Cooldown seconds after consecutive failures (default: 60)")
    parser.add_argument("--max-consecutive-fails", type=int, default=3,
                        help="Consecutive fail threshold to trigger cooldown (default: 3)")

    # 数据源
    parser.add_argument("--test-file", type=str, default=None,
                        help="TripTailor test.json path (auto-detected if not set)")
    parser.add_argument("--info-file", type=str, default=None,
                        help="TripTailor infomation.json path (auto-detected if not set)")

    # 跳过生成
    parser.add_argument("--eval-only", action="store_true",
                        help="Skip generation, evaluate existing result file")
    parser.add_argument("--input", type=str, default=None,
                        help="Existing result file for --eval-only mode")

    # 输出
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory (default: orchestrator/outputs)")

    # API Keys
    parser.add_argument("--deepseek-key", type=str, default=None)
    parser.add_argument("--amap-key", type=str, default=None)

    args = parser.parse_args()

    # 注入 API Keys
    if args.deepseek_key:
        os.environ["DEEPSEEK_API_KEY"] = args.deepseek_key
    if args.amap_key:
        os.environ["AMAP_API_KEY"] = args.amap_key

    plan_key = args.plan_key

    safe_print(f"\n{'='*65}")
    safe_print(f"  Orchestrator Agent - TripTailor Evaluation")
    safe_print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    safe_print(f"{'='*65}")

    # ---- Eval-only 模式 ----
    if args.eval_only:
        if not args.input:
            safe_print("  [ERROR] --eval-only requires --input <result_file>")
            sys.exit(1)

        safe_print(f"\n  [MODE] Eval-only: loading {args.input}")
        with open(args.input, "r", encoding="utf-8") as f:
            results = json.load(f)
        safe_print(f"  Loaded {len(results)} results")

        # 推断 plan_key
        if results:
            for key in results[0].keys():
                if key.endswith("_plan_json"):
                    plan_key = key.replace("_plan_json", "")
                    break
        safe_print(f"  Plan Key: {plan_key}")

        summary = run_triptailor_eval(results, plan_key,
                                      info_file=args.info_file,
                                      output_dir=args.output_dir)
        print_summary(results, summary, plan_key)
        return

    # ---- 正常模式: 生成 + 评测 ----

    # 1. 定位 test.json
    test_file = args.test_file or find_test_json()
    if not test_file or not os.path.exists(test_file):
        safe_print(f"  [ERROR] Cannot find TripTailor test.json")
        safe_print(f"  Expected at: TripTailor/data/test.json")
        safe_print(f"  Or specify: --test-file path/to/test.json")
        sys.exit(1)

    # 2. 加载测试数据 (支持 start/end 分批)
    test_data = load_test_data(test_file, max_samples=-1)  # 先加载全部

    # 应用 start/end 范围
    start_idx = max(args.start - 1, 0)  # 转为 0-based
    if args.end > 0:
        end_idx = args.end
    else:
        end_idx = len(test_data)
    test_data = test_data[start_idx:end_idx]

    # 再应用 max 限制
    if args.max > 0:
        test_data = test_data[:args.max]

    safe_print(f"  Test range: [{start_idx+1}, {min(end_idx, start_idx+len(test_data))}] "
               f"({len(test_data)} samples)")

    # 3. 确定续传文件
    resume_file = None
    if args.resume:
        if args.resume_file:
            resume_file = args.resume_file
        else:
            # 自动检测默认进度文件
            output_base = args.output_dir or str(Path(__file__).parent / "outputs")
            default_progress = os.path.join(output_base, f"{plan_key}_progress.json")
            if os.path.exists(default_progress):
                resume_file = default_progress
                safe_print(f"  [RESUME] Auto-detected: {resume_file}")
            else:
                safe_print(f"  [RESUME] No progress file found, starting fresh")

    # 4. 调用 Agent 生成规划
    results = run_agent_generation(
        test_data,
        plan_key=plan_key,
        output_dir=args.output_dir,
        delay=args.delay,
        retry=args.retry,
        resume_file=resume_file,
        cooldown=args.cooldown,
        max_consecutive_fails=args.max_consecutive_fails,
    )

    # 5. 保存完整结果文件
    output_base = args.output_dir or str(Path(__file__).parent / "outputs")
    os.makedirs(output_base, exist_ok=True)
    result_file = os.path.join(output_base, f"{plan_key}_result.json")
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    safe_print(f"\n  [SAVE] Full results: {result_file}")

    # 6. 运行 TripTailor 评测
    summary = run_triptailor_eval(results, plan_key,
                                  info_file=args.info_file,
                                  output_dir=args.output_dir)

    # 7. 汇总
    print_summary(results, summary, plan_key)

    safe_print(f"  Result file:  {result_file}")
    safe_print(f"  To re-evaluate: python -m orchestrator.batch_eval --eval-only --input {result_file}")


if __name__ == "__main__":
    main()
