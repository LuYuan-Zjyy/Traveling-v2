#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键评测流程脚本 - TripTailor

此脚本包含完整的评测流程:
1. 使用 DeepSeek API 运行 Agent 生成旅行计划
2. 合并结果
3. 运行评测并输出得分

使用方法:
    python run_eval_pipeline.py

会自动从 .env 文件读取 API Key，也可以手动指定:
    python run_eval_pipeline.py --api_key YOUR_DEEPSEEK_API_KEY
"""

import os
import sys
import json
import argparse
from datetime import datetime


def load_env_file():
    """从 .env 文件加载环境变量"""
    # 查找 .env 文件 (当前目录或上级目录)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_paths = [
        os.path.join(script_dir, '.env'),
        os.path.join(script_dir, '..', '.env'),
        os.path.join(script_dir, '..', '..', '.env'),
    ]
    
    for env_path in env_paths:
        if os.path.exists(env_path):
            print(f"📄 加载环境变量: {env_path}")
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        # 移除引号
                        if (value.startswith('"') and value.endswith('"')) or \
                           (value.startswith("'") and value.endswith("'")):
                            value = value[1:-1]
                        os.environ[key] = value
            return True
    return False


# 加载 .env 文件
load_env_file()

# ============================================================
# 配置区域 - 根据需要修改
# ============================================================

CONFIG = {
    # DeepSeek API 配置
    'api_key': '',  # 或者使用环境变量 DEEPSEEK_API_KEY
    'base_url': 'https://api.openai.com/v1',  # DeepSeek API 地址
    'model_name': 'deepseek-chat',  # 模型名称
    
    # 测试配置
    'mode': 'direct',  # 运行模式: 'direct' 或 'workflow'
    'max_samples': 10,  # 测试样本数量，设为 -1 表示全部测试 (共703条)
    
    # 数据路径
    'data_dir': '../data',
    'output_dir': './outputs',
}

# ============================================================


def check_dependencies():
    """检查依赖"""
    required = ['openai', 'pandas', 'fuzzywuzzy', 'tqdm']
    missing = []
    
    for pkg in required:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    
    if missing:
        print(f"❌ 缺少依赖包: {', '.join(missing)}")
        print(f"   请运行: pip install {' '.join(missing)}")
        return False
    
    return True


def load_test_data(data_dir, max_samples=-1):
    """加载测试数据"""
    test_file = os.path.join(data_dir, 'test.json')
    info_file = os.path.join(data_dir, 'infomation.json')
    
    if not os.path.exists(test_file):
        print(f"❌ 找不到测试数据: {test_file}")
        return None, None
    
    with open(test_file, 'r', encoding='utf-8') as f:
        test_data = json.load(f)
    
    if max_samples > 0:
        test_data = test_data[:max_samples]
    
    info_data = None
    if os.path.exists(info_file):
        with open(info_file, 'r', encoding='utf-8') as f:
            info_data = json.load(f)
    
    return test_data, info_data


def call_llm(client, model, prompt, system_prompt=None):
    """调用 LLM"""
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.7,
    )
    
    return response.choices[0].message.content


def generate_plan_direct(client, model, query, given_info):
    """直接生成旅行计划 (direct 模式)"""
    prompt = f"""你是一个专业的旅行规划师。请根据用户需求和提供的信息，生成详细的旅行计划。

用户需求: {query}

可用信息:
{given_info}

请按以下JSON格式输出旅行计划:
{{
    "hotel": [{{"day": 1, "name": "酒店名称", "price_per_night": 价格}}],
    "transportation": [
        {{"day": 1, "mode": "Train/Flight", "route": "出发地 to 目的地", "number": "车次/航班号", "time": "时间", "price": 价格}},
        {{"day": N, "mode": "Train/Flight", "route": "目的地 to 出发地", "number": "车次/航班号", "time": "时间", "price": 价格}}
    ],
    "itinerary": {{
        "day_1": [{{"time": "时间", "location": "地点", "price": 价格, "action": "sightseeing/dining"}}],
        "day_2": [...],
        ...
    }}
}}

只输出JSON，不要其他内容。"""

    response = call_llm(client, model, prompt)
    
    # 尝试提取JSON
    try:
        # 查找JSON内容
        if '```json' in response:
            response = response.split('```json')[1].split('```')[0]
        elif '```' in response:
            response = response.split('```')[1].split('```')[0]
        
        # 验证JSON
        json.loads(response)
        return response
    except:
        return response


def run_pipeline(api_key, base_url, model_name, test_data, info_data, output_dir, mode='direct'):
    """运行评测流水线"""
    from openai import OpenAI
    from tqdm import tqdm
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 初始化客户端
    print(f"\n🔗 连接 API: {base_url}")
    print(f"🤖 使用模型: {model_name}")
    
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    
    # 生成计划
    results = []
    plan_key = f"{model_name.replace('-', '_')}_{mode}"
    
    print(f"\n⏳ 开始生成旅行计划 (共 {len(test_data)} 条)...\n")
    
    for item in tqdm(test_data, desc="生成计划"):
        pid = item['pid']
        query = item['query']
        
        # 获取给定信息
        given_info = ""
        if info_data and str(pid) in info_data:
            given_info = json.dumps(info_data[str(pid)], ensure_ascii=False, indent=2)
        
        try:
            # 生成计划
            plan_json = generate_plan_direct(client, model_name, query, given_info)
            
            # 保存结果
            result = item.copy()
            result[f'{plan_key}_plan'] = plan_json
            result[f'{plan_key}_plan_json'] = plan_json
            results.append(result)
            
        except Exception as e:
            print(f"\n⚠️ 样本 {pid} 生成失败: {e}")
            continue
    
    # 保存结果
    output_file = os.path.join(output_dir, f'{plan_key}_result.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 计划生成完成，已保存到: {output_file}")
    
    return results, plan_key, output_file


def run_evaluation(results, plan_key, info_file):
    """运行评测"""
    # 导入评测模块
    sys.path.append(os.path.join(os.path.dirname(__file__), 'eval'))
    from eval.simple_eval import StrictEvaluator, print_results
    
    print(f"\n⏳ 正在评测...")
    
    evaluator = StrictEvaluator(
        info_file=info_file
    )
    
    summary = evaluator.evaluate_batch(results, plan_key)
    print_results(summary, plan_key)
    
    return summary


def main():
    parser = argparse.ArgumentParser(description='TripTailor 一键评测流程')
    parser.add_argument('--api_key', type=str, default='',
                        help='DeepSeek API Key (也可设置环境变量 DEEPSEEK_API_KEY)')
    parser.add_argument('--base_url', type=str, default=CONFIG['base_url'],
                        help='API Base URL')
    parser.add_argument('--model', type=str, default=CONFIG['model_name'],
                        help='模型名称')
    parser.add_argument('--samples', type=int, default=CONFIG['max_samples'],
                        help='测试样本数量 (-1 为全部)')
    parser.add_argument('--mode', type=str, default=CONFIG['mode'],
                        choices=['direct', 'workflow'],
                        help='运行模式')
    parser.add_argument('--skip_generation', action='store_true',
                        help='跳过计划生成，直接评测已有结果')
    parser.add_argument('--input_file', type=str, default='',
                        help='已有结果文件 (与 --skip_generation 配合使用)')
    
    args = parser.parse_args()
    
    print("\n" + "=" * 60)
    print("  TripTailor 一键评测流程")
    print("=" * 60)
    
    # 获取 API Key (支持多种环境变量名)
    api_key = (args.api_key or 
               os.environ.get('DEEPSEEK_API') or 
               os.environ.get('DEEPSEEK_API_KEY') or 
               CONFIG['api_key'])
    
    # 获取搜索 API Key (用于事实验证)
    search_api_key = os.environ.get('SEARCH_API') or os.environ.get('SEARCH_API_KEY')
    
    if not api_key and not args.skip_generation:
        print("\n❌ 错误: 未设置 API Key")
        print("   请使用以下方式之一设置:")
        print("   1. 在 .env 文件中设置 DEEPSEEK_API=your_key")
        print("   2. 命令行参数: --api_key YOUR_KEY")
        print("   3. 环境变量: set DEEPSEEK_API=YOUR_KEY")
        sys.exit(1)
    
    if api_key:
        print(f"✅ API Key 已加载 (长度: {len(api_key)})")
    
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 数据目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, CONFIG['data_dir'])
    output_dir = os.path.join(script_dir, CONFIG['output_dir'])
    info_file = os.path.join(data_dir, 'infomation.json')
    
    if args.skip_generation:
        # 直接评测已有结果
        if not args.input_file:
            print("❌ 使用 --skip_generation 时需要指定 --input_file")
            sys.exit(1)
        
        print(f"\n📁 加载已有结果: {args.input_file}")
        with open(args.input_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        # 推断 plan_key
        for key in results[0].keys():
            if key.endswith('_plan_json'):
                plan_key = key.replace('_plan_json', '')
                break
        else:
            plan_key = 'unknown'
        
    else:
        # 加载测试数据
        print(f"\n📁 加载数据...")
        test_data, info_data = load_test_data(data_dir, args.samples)
        
        if test_data is None:
            sys.exit(1)
        
        print(f"   测试样本: {len(test_data)} 条")
        
        # 运行生成流程
        results, plan_key, output_file = run_pipeline(
            api_key=api_key,
            base_url=args.base_url,
            model_name=args.model,
            test_data=test_data,
            info_data=info_data,
            output_dir=output_dir,
            mode=args.mode
        )
    
    # 运行评测
    if results:
        summary = run_evaluation(results, plan_key, info_file)
        
        # 保存评测结果
        eval_output = os.path.join(output_dir, f'{plan_key}_eval_result.json')
        with open(eval_output, 'w', encoding='utf-8') as f:
            json.dump({
                'plan_key': plan_key,
                'total_score': summary['total_score'],
                'metrics': summary['metrics'],
                'timestamp': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 评测结果已保存到: {eval_output}")
    
    print("\n✅ 流程完成!\n")


if __name__ == '__main__':
    main()



