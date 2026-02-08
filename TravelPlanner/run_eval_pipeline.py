#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键评测流程脚本 - TravelPlanner

此脚本包含完整的评测流程:
1. 使用 DeepSeek API 以 sole-planning 模式生成旅行计划
2. 解析自然语言计划为 JSON 格式
3. 组合为提交文件 (JSONL)
4. 运行 Commonsense + Hard Constraint 评测
5. 输出最终得分

使用方法:
    python run_eval_pipeline.py

会自动从 .env 文件读取 DEEPSEEK_API 和 SEARCH_API。
也可以手动指定:
    python run_eval_pipeline.py --api_key YOUR_KEY

评测指标 (与 TripTailor 不同):
    - Delivery Rate: 成功生成计划的比例
    - Commonsense Constraint Micro/Macro Pass Rate: 常识约束通过率
      (城市路线、沙盒约束、餐厅/景点多样性、交通一致性、住宿最低天数、信息完整性)
    - Hard Constraint Micro/Macro Pass Rate: 硬约束通过率
      (预算、房间规则、菜系、房型、交通方式)
    - Final Pass Rate: 最终通过率 (两类约束全部通过)
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime
from tqdm import tqdm


# ============================================================
# .env 加载
# ============================================================

def load_env_file():
    """从 .env 文件加载环境变量"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_paths = [
        os.path.join(script_dir, '.env'),
        os.path.join(script_dir, '..', '.env'),
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            print(f"  Loading .env: {env_path}")
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        os.environ[key] = value
            return True
    return False


load_env_file()


# ============================================================
# 配置区域
# ============================================================

CONFIG = {
    # DeepSeek API 配置
    'api_key': '',
    'base_url': 'https://api.deepseek.com/v1',
    'model_name': 'deepseek-chat',

    # 评测配置
    'set_type': 'validation',       # 'train' (45), 'validation' (180), 'test' (1000)
    'strategy': 'direct',           # 'direct', 'cot', 'react', 'reflexion'
    'mode': 'sole-planning',        # 'sole-planning' 或 'two-stage'
    'max_samples': -1,              # -1 表示全部测试

    # 路径
    'output_dir': './outputs',
    'ref_info_dir': './database',
}

# 数据集大小
DATASET_SIZES = {
    'train': 45,
    'validation': 180,
    'test': 1000,
}

# 约束总数 (用于 Micro Pass Rate 计算)
CONSTRAINT_TOTALS = {
    'train':      {'commonsense': 360,  'hard': 105},
    'validation': {'commonsense': 1440, 'hard': 420},
    'test':       {'commonsense': 8000, 'hard': 2290},
}


# ============================================================
# 依赖检查
# ============================================================

def check_dependencies():
    """检查依赖"""
    required = ['openai', 'pandas', 'tqdm', 'datasets']
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"  Missing dependencies: {', '.join(missing)}")
        print(f"  Run: pip install {' '.join(missing)}")
        return False
    return True


# ============================================================
# 数据加载
# ============================================================

def load_query_data(set_type, max_samples=-1):
    """加载 HuggingFace 上的查询数据"""
    from datasets import load_dataset
    print(f"  Loading {set_type} dataset from HuggingFace...")
    ds = load_dataset('osunlp/TravelPlanner', set_type)[set_type]
    data = list(ds)
    if max_samples > 0:
        data = data[:max_samples]
    print(f"  Loaded {len(data)} samples")
    return data


def load_ref_info(set_type, ref_info_dir):
    """加载参考信息"""
    ref_file = os.path.join(ref_info_dir, f'{set_type}_ref_info.jsonl')
    if not os.path.exists(ref_file):
        print(f"  Warning: ref info file not found: {ref_file}")
        return None
    data = []
    with open(ref_file, 'r', encoding='utf-8') as f:
        for line in f.read().strip().split('\n'):
            if line:
                data.append(json.loads(line))
    print(f"  Loaded {len(data)} ref info entries")
    return data


def load_line_json_data(filename):
    """加载 JSONL 文件"""
    data = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f.read().strip().split('\n'):
            if line:
                data.append(json.loads(line))
    return data


# ============================================================
# 计划生成 (Sole-Planning 模式)
# ============================================================

PLANNER_PROMPT = """You are a proficient planner. Based on the provided information and query, please give me a detailed plan, including specifics such as flight numbers (e.g., F0123456), restaurant names, and accommodation names. Note that all the information in your plan should be derived from the provided data. You must adhere to the format given in the example. Additionally, all details should align with commonsense. The symbol '-' indicates that information is unnecessary. For example, in the provided sample, you do not need to plan after returning to the departure city. When you travel to two cities in one day, you should note it in the 'Current City' section as in the example (i.e., from A to B).

***** Example *****
Query: Could you create a travel plan for 7 people from Ithaca to Charlotte spanning 3 days, from March 8th to March 14th, 2022, with a budget of $30,200?
Travel Plan:
Day 1:
Current City: from Ithaca to Charlotte
Transportation: Flight Number: F3633413, from Ithaca to Charlotte, Departure Time: 05:38, Arrival Time: 07:46
Breakfast: Nagaland's Kitchen, Charlotte
Attraction: The Charlotte Museum of History, Charlotte
Lunch: Cafe Maple Street, Charlotte
Dinner: Bombay Vada Pav, Charlotte
Accommodation: Affordable Spacious Refurbished Room in Bushwick!, Charlotte

Day 2:
Current City: Charlotte
Transportation: -
Breakfast: Olive Tree Cafe, Charlotte
Attraction: The Mint Museum, Charlotte;Romare Bearden Park, Charlotte.
Lunch: Birbal Ji Dhaba, Charlotte
Dinner: Pind Balluchi, Charlotte
Accommodation: Affordable Spacious Refurbished Room in Bushwick!, Charlotte

Day 3:
Current City: from Charlotte to Ithaca
Transportation: Flight Number: F3786167, from Charlotte to Ithaca, Departure Time: 21:42, Arrival Time: 23:26
Breakfast: Subway, Charlotte
Attraction: Books Monument, Charlotte.
Lunch: Olive Tree Cafe, Charlotte
Dinner: Kylin Skybar, Charlotte
Accommodation: -

***** Example Ends *****

Given information: {text}
Query: {query}
Travel Plan:"""


PARSE_PROMPT = """Please assist me in extracting valid information from a given natural language text and reconstructing it in JSON format, as demonstrated in the following example. If transportation details indicate a journey from one city to another (e.g., from A to B), the 'current_city' should be updated to the destination city (in this case, B). Use a ';' to separate different attractions, with each attraction formatted as 'Name, City'. If there's information about transportation, ensure that the 'current_city' aligns with the destination mentioned in the transportation details (i.e., the current city should follow the format 'from A to B'). Also, ensure that all flight numbers and costs are followed by a colon (i.e., 'Flight Number:' and 'Cost:'), consistent with the provided example. Each item should include ['day', 'current_city', 'transportation', 'breakfast', 'attraction', 'lunch', 'dinner', 'accommodation']. Replace non-specific information like 'eat at home/on the road' with '-'. Additionally, delete any '$' symbols.
-----EXAMPLE-----
 [{{
        "days": 1,
        "current_city": "from Dallas to Peoria",
        "transportation": "Flight Number: 4044830, from Dallas to Peoria, Departure Time: 13:10, Arrival Time: 15:01",
        "breakfast": "-",
        "attraction": "Peoria Historical Society, Peoria;Peoria Holocaust Memorial, Peoria;",
        "lunch": "-",
        "dinner": "Tandoor Ka Zaika, Peoria",
        "accommodation": "Bushwick Music Mansion, Peoria"
    }},
    {{
        "days": 2,
        "current_city": "Peoria",
        "transportation": "-",
        "breakfast": "Tandoor Ka Zaika, Peoria",
        "attraction": "Peoria Riverfront Park, Peoria;The Peoria PlayHouse, Peoria;Glen Oak Park, Peoria;",
        "lunch": "Cafe Hashtag LoL, Peoria",
        "dinner": "The Curzon Room - Maidens Hotel, Peoria",
        "accommodation": "Bushwick Music Mansion, Peoria"
    }},
    {{
        "days": 3,
        "current_city": "from Peoria to Dallas",
        "transportation": "Flight Number: 4045904, from Peoria to Dallas, Departure Time: 07:09, Arrival Time: 09:20",
        "breakfast": "-",
        "attraction": "-",
        "lunch": "-",
        "dinner": "-",
        "accommodation": "-"
    }}]
-----EXAMPLE END-----

Text:
{text}
JSON:
"""


def call_llm(client, model, prompt, temperature=0):
    """调用 LLM"""
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return response.choices[0].message.content


def generate_plans(client, model, query_data_list, ref_info_list, output_dir, set_type, max_samples=-1):
    """生成旅行计划"""
    os.makedirs(output_dir, exist_ok=True)

    results_file = os.path.join(output_dir, f'{set_type}_plans_raw.jsonl')
    # 加载已有进度
    existing = {}
    if os.path.exists(results_file):
        for line in open(results_file, 'r', encoding='utf-8'):
            if line.strip():
                item = json.loads(line)
                existing[item['idx']] = item
        print(f"  Resuming: found {len(existing)} existing results")

    total = len(query_data_list)
    if max_samples > 0:
        total = min(total, max_samples)

    with open(results_file, 'a', encoding='utf-8') as f_out:
        for i in tqdm(range(total), desc="Generating plans"):
            idx = i + 1
            if idx in existing:
                continue

            query_data = query_data_list[i]
            query = query_data['query']

            # 获取参考信息
            if ref_info_list and i < len(ref_info_list):
                reference_info = json.dumps(ref_info_list[i], ensure_ascii=False)
            elif 'reference_information' in query_data and query_data['reference_information']:
                reference_info = query_data['reference_information']
            else:
                reference_info = "No reference information available."

            try:
                prompt = PLANNER_PROMPT.format(text=reference_info, query=query)
                plan_text = call_llm(client, model, prompt)
            except Exception as e:
                print(f"\n  Sample {idx} generation failed: {e}")
                plan_text = ""

            result = {"idx": idx, "query": query, "plan_text": plan_text}
            f_out.write(json.dumps(result, ensure_ascii=False) + '\n')
            f_out.flush()
            existing[idx] = result

    print(f"  Raw plans saved to: {results_file}")
    return results_file


def parse_plans(client, model, raw_plans_file, output_dir, set_type):
    """将自然语言计划解析为 JSON 格式"""
    raw_plans = load_line_json_data(raw_plans_file)
    parsed_file = os.path.join(output_dir, f'{set_type}_plans_parsed.jsonl')

    # 加载已有进度
    existing = {}
    if os.path.exists(parsed_file):
        for line in open(parsed_file, 'r', encoding='utf-8'):
            if line.strip():
                item = json.loads(line)
                existing[item['idx']] = item
        print(f"  Resuming parse: found {len(existing)} existing parsed results")

    with open(parsed_file, 'a', encoding='utf-8') as f_out:
        for item in tqdm(raw_plans, desc="Parsing plans"):
            idx = item['idx']
            if idx in existing:
                continue

            plan_text = item.get('plan_text', '')
            parsed_plan = None

            if plan_text and plan_text != "":
                try:
                    prompt = PARSE_PROMPT.format(text=plan_text)
                    result_text = call_llm(client, model, prompt)

                    # 提取 JSON
                    if '```json' in result_text:
                        json_str = result_text.split('```json')[1].split('```')[0]
                    elif '```' in result_text:
                        json_str = result_text.split('```')[1].split('```')[0]
                    else:
                        json_str = result_text

                    parsed_plan = json.loads(json_str)
                except Exception as e:
                    print(f"\n  Sample {idx} parse failed: {e}")
                    parsed_plan = None

            result = {"idx": idx, "query": item['query'], "plan": parsed_plan}
            f_out.write(json.dumps(result, ensure_ascii=False) + '\n')
            f_out.flush()
            existing[idx] = result

    print(f"  Parsed plans saved to: {parsed_file}")
    return parsed_file


def create_submission(parsed_file, output_dir, set_type, model_name, strategy):
    """创建提交文件"""
    parsed_plans = load_line_json_data(parsed_file)
    # 按 idx 排序
    parsed_plans.sort(key=lambda x: x['idx'])

    submission_file = os.path.join(output_dir, f'{set_type}_{model_name}_{strategy}_submission.jsonl')
    with open(submission_file, 'w', encoding='utf-8') as f:
        for item in parsed_plans:
            submission = {
                "idx": item['idx'],
                "query": item['query'],
                "plan": item['plan']
            }
            f.write(json.dumps(submission, ensure_ascii=False) + '\n')

    print(f"  Submission file saved to: {submission_file}")
    return submission_file


# ============================================================
# 评测
# ============================================================

def run_evaluation(submission_file, set_type):
    """运行评测"""
    print(f"\n  Running evaluation on {set_type} set...")

    # 尝试使用完整评测模块
    eval_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'evaluation')
    sys.path.insert(0, eval_dir)
    orig_cwd = os.getcwd()

    try:
        os.chdir(eval_dir)
        from eval import eval_score
        scores, detailed_scores = eval_score(set_type, file_path=submission_file)
        os.chdir(orig_cwd)
        return scores, detailed_scores
    except Exception as e:
        os.chdir(orig_cwd)
        print(f"  Full evaluation failed ({e}), falling back to simple evaluation...")

    # 简化评测
    try:
        os.chdir(eval_dir)
        from simple_eval import TravelPlannerEvaluator, print_results as simple_print
        evaluator = TravelPlannerEvaluator(set_type=set_type)
        if not evaluator.load_data():
            print("  ERROR: Cannot load query data")
            return None, None

        tested_plans = load_line_json_data(submission_file)
        summary = evaluator.evaluate_batch(tested_plans)
        os.chdir(orig_cwd)

        # 转换为统一格式
        m = summary['metrics']
        scores = {
            'Delivery Rate': m['delivery_rate'],
            'Commonsense Constraint Micro Pass Rate': m['commonsense_micro'],
            'Commonsense Constraint Macro Pass Rate': m['commonsense_macro'],
            'Hard Constraint Micro Pass Rate': m['hard_micro'],
            'Hard Constraint Macro Pass Rate': m['hard_macro'],
            'Final Pass Rate': m['final_pass_rate'],
        }
        return scores, summary
    except Exception as e2:
        os.chdir(orig_cwd)
        print(f"  Simple evaluation also failed: {e2}")
        import traceback
        traceback.print_exc()
        return None, None


def print_results(scores, set_type, detailed_scores=None):
    """打印评测结果"""
    total_samples = DATASET_SIZES.get(set_type, '?')

    print("\n" + "=" * 65)
    print(f"  TravelPlanner Evaluation Results - {set_type}")
    print("=" * 65)
    print(f"\n  Dataset: {set_type} ({total_samples} samples)")

    if scores is None:
        print("\n  ERROR: Evaluation failed")
        print("=" * 65)
        return

    print("\n" + "-" * 65)
    print("  Core Metrics")
    print("-" * 65)
    for key, value in scores.items():
        print(f"  {key:50s} {value*100:6.2f}%")

    # 计算总分
    m = scores
    total_score = (
        m.get('Delivery Rate', 0) * 10 +
        m.get('Commonsense Constraint Micro Pass Rate', 0) * 20 +
        m.get('Commonsense Constraint Macro Pass Rate', 0) * 20 +
        m.get('Hard Constraint Micro Pass Rate', 0) * 15 +
        m.get('Hard Constraint Macro Pass Rate', 0) * 15 +
        m.get('Final Pass Rate', 0) * 20
    )
    print(f"\n  {'Total Score':50s} {total_score:6.2f} / 100")

    if detailed_scores and isinstance(detailed_scores, dict):
        print("\n" + "-" * 65)
        print("  Detailed Constraint Breakdown")
        print("-" * 65)

        # Commonsense 详情
        if 'Commonsense Constraint' in detailed_scores:
            print("\n  [Commonsense Constraints]")
            cc = detailed_scores['Commonsense Constraint']
            for level in cc:
                for day in cc[level]:
                    for constraint_name, stats in cc[level][day].items():
                        if isinstance(stats, dict) and 'true' in stats:
                            total = stats.get('total', stats['true'] + stats['false'])
                            if total > 0:
                                rate = stats['true'] / total * 100
                                print(f"    {level}/{day}d {constraint_name:35s} {stats['true']}/{total} ({rate:.1f}%)")

        # Hard 详情
        if 'Hard Constraint' in detailed_scores:
            print("\n  [Hard Constraints]")
            hc = detailed_scores['Hard Constraint']
            for level in hc:
                for day in hc[level]:
                    for constraint_name, stats in hc[level][day].items():
                        if isinstance(stats, dict) and 'true' in stats:
                            total = stats.get('total', stats['true'] + stats['false'])
                            if total > 0:
                                rate = stats['true'] / total * 100
                                print(f"    {level}/{day}d {constraint_name:35s} {stats['true']}/{total} ({rate:.1f}%)")

    print("\n" + "=" * 65)
    return total_score


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='TravelPlanner Evaluation Pipeline')
    parser.add_argument('--api_key', type=str, default='',
                        help='DeepSeek API Key')
    parser.add_argument('--base_url', type=str, default=CONFIG['base_url'],
                        help='API Base URL')
    parser.add_argument('--model', type=str, default=CONFIG['model_name'],
                        help='Model name')
    parser.add_argument('--set_type', type=str, default=CONFIG['set_type'],
                        choices=['train', 'validation', 'test'],
                        help='Dataset type')
    parser.add_argument('--strategy', type=str, default=CONFIG['strategy'],
                        choices=['direct', 'cot'],
                        help='Planning strategy')
    parser.add_argument('--samples', type=int, default=CONFIG['max_samples'],
                        help='Max samples (-1 for all)')
    parser.add_argument('--skip_generation', action='store_true',
                        help='Skip plan generation, evaluate existing results')
    parser.add_argument('--skip_parse', action='store_true',
                        help='Skip parsing, use already parsed plans')
    parser.add_argument('--input_file', type=str, default='',
                        help='Existing submission file for evaluation (with --skip_generation)')

    args = parser.parse_args()

    print("\n" + "=" * 65)
    print("  TravelPlanner Evaluation Pipeline")
    print("=" * 65)

    # 获取 API Key
    api_key = (args.api_key or
               os.environ.get('DEEPSEEK_API') or
               os.environ.get('DEEPSEEK_API_KEY') or
               CONFIG['api_key'])

    if not api_key and not args.skip_generation:
        print("\n  ERROR: No API Key found")
        print("   Set in .env: DEEPSEEK_API=your_key")
        print("   Or: --api_key YOUR_KEY")
        sys.exit(1)

    if api_key:
        print(f"  API Key loaded (length: {len(api_key)})")

    # 检查依赖
    if not check_dependencies():
        sys.exit(1)

    # 路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(script_dir, CONFIG['output_dir'])
    ref_info_dir = os.path.join(script_dir, CONFIG['ref_info_dir'])
    os.makedirs(output_dir, exist_ok=True)

    set_type = args.set_type
    model_name = args.model.replace('-', '_').replace('.', '_')
    strategy = args.strategy
    expected_samples = DATASET_SIZES.get(set_type, 0)

    print(f"\n  Config:")
    print(f"    Dataset:  {set_type} ({expected_samples} samples)")
    print(f"    Model:    {args.model}")
    print(f"    Strategy: {strategy}")
    print(f"    Samples:  {'all' if args.samples == -1 else args.samples}")

    if args.skip_generation and args.input_file:
        # 直接评测已有文件
        submission_file = args.input_file
        if not os.path.exists(submission_file):
            print(f"\n  ERROR: File not found: {submission_file}")
            sys.exit(1)
        print(f"\n  Using existing submission: {submission_file}")
    else:
        # 完整流程
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=args.base_url)
        print(f"\n  API: {args.base_url}")
        print(f"  Model: {args.model}")

        # Step 1: 加载数据
        print(f"\n--- Step 1: Load data ---")
        query_data_list = load_query_data(set_type, args.samples)
        ref_info_list = load_ref_info(set_type, ref_info_dir)

        # Step 2: 生成计划
        print(f"\n--- Step 2: Generate plans ---")
        raw_plans_file = generate_plans(
            client, args.model, query_data_list, ref_info_list,
            output_dir, set_type, args.samples
        )

        # Step 3: 解析计划
        if not args.skip_parse:
            print(f"\n--- Step 3: Parse plans to JSON ---")
            parsed_file = parse_plans(client, args.model, raw_plans_file, output_dir, set_type)
        else:
            parsed_file = os.path.join(output_dir, f'{set_type}_plans_parsed.jsonl')
            print(f"\n--- Step 3: Skip parsing, using {parsed_file} ---")

        # Step 4: 创建提交文件
        print(f"\n--- Step 4: Create submission file ---")
        submission_file = create_submission(parsed_file, output_dir, set_type, model_name, strategy)

    # Step 5: 评测
    print(f"\n--- Step 5: Evaluate ---")
    scores, detailed_scores = run_evaluation(submission_file, set_type)
    total_score = print_results(scores, set_type, detailed_scores)

    # 保存结果
    if scores:
        eval_output = os.path.join(output_dir, f'{set_type}_{model_name}_{strategy}_eval_result.json')
        with open(eval_output, 'w', encoding='utf-8') as f:
            json.dump({
                'set_type': set_type,
                'model': args.model,
                'strategy': strategy,
                'total_score': total_score,
                'scores': {k: round(v * 100, 4) for k, v in scores.items()},
                'timestamp': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        print(f"\n  Results saved to: {eval_output}")

    print("\n  Pipeline complete!\n")


if __name__ == '__main__':
    main()
