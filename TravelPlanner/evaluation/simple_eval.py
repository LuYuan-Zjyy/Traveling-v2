#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TravelPlanner 简化评测脚本

评估两类约束：
1. Commonsense Constraint (常识约束): 城市路线、餐厅/景点多样性、沙盒约束等
2. Hard Constraint (硬约束): 预算、房间规则、菜系、交通等

使用方法:
    python simple_eval.py --set_type validation --evaluation_file_path <文件路径>

指标说明:
    - Delivery Rate: 成功生成计划的比例
    - Commonsense Micro: 常识约束通过率 (单项)
    - Commonsense Macro: 常识约束通过率 (全部通过)
    - Hard Micro: 硬约束通过率 (单项)
    - Hard Macro: 硬约束通过率 (全部通过)
    - Final Pass Rate: 最终通过率 (两类约束全部通过)
"""

import os
import sys
import json
import argparse
from datetime import datetime

# 添加路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from tqdm import tqdm

# 导入原有评测模块
EVAL_AVAILABLE = False
commonsense_eval = None
hard_eval = None

try:
    from commonsense_constraint import evaluation as commonsense_eval
    from hard_constraint import evaluation as hard_eval
    EVAL_AVAILABLE = True
except Exception as e:
    print(f"提示: 完整评测模块不可用 ({e})，将使用简化评测")

# 事实验证模块 (可选)
try:
    from fact_checker import TravelPlannerFactChecker
    FACT_CHECKER_AVAILABLE = True
except ImportError:
    FACT_CHECKER_AVAILABLE = False


def load_line_json_data(filename):
    """加载 JSONL 文件"""
    data = []
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f.read().strip().split('\n'):
            if line:
                data.append(json.loads(line))
    return data


def load_query_data(set_type):
    """加载查询数据"""
    try:
        from datasets import load_dataset
        if set_type == 'train':
            return list(load_dataset('osunlp/TravelPlanner', 'train')['train'])
        elif set_type == 'validation':
            return list(load_dataset('osunlp/TravelPlanner', 'validation')['validation'])
        elif set_type == 'test':
            return list(load_dataset('osunlp/TravelPlanner', 'test')['test'])
    except Exception as e:
        print(f"错误: 无法加载数据集 - {e}")
        return None


class TravelPlannerEvaluator:
    """TravelPlanner 评估器"""
    
    def __init__(self, set_type='validation', enable_fact_check=False, search_engine='duckduckgo'):
        self.set_type = set_type
        self.query_data = None
        self.fact_checker = None
        
        # 数据集大小
        self.dataset_sizes = {
            'train': 45,
            'validation': 180,
            'test': 1000
        }
        
        # 约束总数
        self.constraint_totals = {
            'train': {'commonsense': 360, 'hard': 105},
            'validation': {'commonsense': 1440, 'hard': 420},
            'test': {'commonsense': 8000, 'hard': 2290}
        }
        
        # 事实验证
        if enable_fact_check and FACT_CHECKER_AVAILABLE:
            self.fact_checker = TravelPlannerFactChecker(search_engine=search_engine)
            print("[OK] Fact accuracy verification enabled")
    
    def load_data(self):
        """加载查询数据"""
        print(f"正在加载 {self.set_type} 数据集...")
        self.query_data = load_query_data(self.set_type)
        if self.query_data:
            print(f"成功加载 {len(self.query_data)} 条数据")
        return self.query_data is not None
    
    def evaluate_single(self, query_data, tested_plan):
        """评估单个计划"""
        result = {
            'has_plan': False,
            'commonsense': None,
            'hard': None,
            'commonsense_pass': False,
            'hard_pass': False,
            'final_pass': False,
            'basic_checks': {}
        }
        
        # 解析数据
        if isinstance(query_data, str):
            query_data = eval(query_data)
        if isinstance(tested_plan, str):
            tested_plan = eval(tested_plan)
        if isinstance(query_data.get('local_constraint'), str):
            query_data['local_constraint'] = eval(query_data['local_constraint'])
        
        # 检查是否有计划
        if not tested_plan.get('plan'):
            return result
        
        result['has_plan'] = True
        plan = tested_plan['plan']
        
        # 如果完整评测模块可用，使用它
        if EVAL_AVAILABLE and commonsense_eval and hard_eval:
            try:
                result['commonsense'] = commonsense_eval(query_data, plan)
            except Exception as e:
                result['commonsense'] = None
            
            if (result['commonsense'] and 
                result['commonsense'].get('is_not_absent', (False,))[0] and 
                result['commonsense'].get('is_valid_information_in_sandbox', (False,))[0]):
                try:
                    result['hard'] = hard_eval(query_data, plan)
                except Exception as e:
                    result['hard'] = None
            
            if result['commonsense']:
                result['commonsense_pass'] = all(
                    v[0] is None or v[0] == True 
                    for v in result['commonsense'].values()
                )
            
            if result['hard']:
                result['hard_pass'] = all(
                    v[0] is None or v[0] == True 
                    for v in result['hard'].values()
                )
        else:
            # 简化评测 (无需数据库)
            result['basic_checks'] = self._basic_evaluation(query_data, plan)
            result['commonsense_pass'] = result['basic_checks'].get('basic_pass', False)
            result['hard_pass'] = result['basic_checks'].get('constraints_pass', False)
        
        result['final_pass'] = result['commonsense_pass'] and result['hard_pass']
        
        return result
    
    def _basic_evaluation(self, query_data, plan):
        """简化评测 (无需数据库)"""
        checks = {
            'has_days': False,
            'has_meals': False,
            'has_attractions': False,
            'has_accommodation': False,
            'has_transportation': False,
            'no_duplicate_restaurants': True,
            'no_duplicate_attractions': True,
            'basic_pass': False,
            'constraints_pass': False
        }
        
        if not plan or not isinstance(plan, list):
            return checks
        
        expected_days = query_data.get('days', len(plan))
        checks['has_days'] = len(plan) >= expected_days
        
        restaurants = set()
        attractions = set()
        
        for day_plan in plan:
            if not isinstance(day_plan, dict):
                continue
            
            # 检查餐饮
            for meal in ['breakfast', 'lunch', 'dinner']:
                if day_plan.get(meal) and day_plan[meal] != '-':
                    checks['has_meals'] = True
                    # 检查重复
                    if day_plan[meal] in restaurants:
                        checks['no_duplicate_restaurants'] = False
                    restaurants.add(day_plan[meal])
            
            # 检查景点
            if day_plan.get('attraction') and day_plan['attraction'] != '-':
                checks['has_attractions'] = True
                for attr in day_plan['attraction'].split(';'):
                    attr = attr.strip()
                    if attr:
                        if attr in attractions:
                            checks['no_duplicate_attractions'] = False
                        attractions.add(attr)
            
            # 检查住宿
            if day_plan.get('accommodation') and day_plan['accommodation'] != '-':
                checks['has_accommodation'] = True
            
            # 检查交通
            if day_plan.get('transportation') and day_plan['transportation'] != '-':
                checks['has_transportation'] = True
        
        # 基础通过条件
        checks['basic_pass'] = (
            checks['has_days'] and 
            checks['has_meals'] and 
            checks['has_attractions'] and
            checks['no_duplicate_restaurants'] and
            checks['no_duplicate_attractions']
        )
        
        # 约束通过条件 (简化版)
        checks['constraints_pass'] = checks['basic_pass'] and checks['has_accommodation']
        
        return checks
    
    def evaluate_batch(self, tested_plans, fact_check_samples=5):
        """批量评估"""
        if not self.query_data:
            return None
        
        results = []
        delivery_count = 0
        commonsense_pass_count = 0
        hard_pass_count = 0
        final_pass_count = 0
        
        # 统计约束通过情况
        commonsense_items = {'pass': 0, 'total': 0}
        hard_items = {'pass': 0, 'total': 0}
        
        # 事实验证统计
        fact_results = []
        fact_checked_count = 0
        
        for idx in tqdm(range(len(self.query_data)), desc="评估中"):
            query = self.query_data[idx]
            plan = tested_plans[idx] if idx < len(tested_plans) else {'plan': None}
            
            result = self.evaluate_single(query, plan)
            results.append(result)
            
            if result['has_plan']:
                delivery_count += 1
            
            if result['commonsense_pass']:
                commonsense_pass_count += 1
            
            if result['hard_pass']:
                hard_pass_count += 1
            
            if result['final_pass']:
                final_pass_count += 1
            
            # 统计各项约束
            if result['commonsense']:
                for key, val in result['commonsense'].items():
                    if val[0] is not None:
                        commonsense_items['total'] += 1
                        if val[0]:
                            commonsense_items['pass'] += 1
            
            if result['hard']:
                for key, val in result['hard'].items():
                    if val[0] is not None:
                        hard_items['total'] += 1
                        if val[0]:
                            hard_items['pass'] += 1
            
            # 事实验证 (只验证前 N 个有计划的样本)
            if self.fact_checker and result['has_plan'] and fact_checked_count < fact_check_samples:
                try:
                    plan_data = plan.get('plan', [])
                    if plan_data:
                        fact_result = self.fact_checker.verify_plan(plan_data, max_checks=10)
                        fact_results.append(fact_result)
                        fact_checked_count += 1
                        print(f"   [FACT] Sample {idx+1} fact accuracy: {fact_result['accuracy']*100:.1f}%")
                except Exception as e:
                    pass
        
        # 计算指标
        total = self.dataset_sizes.get(self.set_type, len(self.query_data))
        
        # 事实准确度
        avg_fact_accuracy = (
            sum(r['accuracy'] for r in fact_results) / len(fact_results)
            if fact_results else 1.0
        )
        
        summary = {
            'set_type': self.set_type,
            'total_samples': total,
            'metrics': {
                'delivery_rate': delivery_count / total,
                'commonsense_micro': commonsense_items['pass'] / max(commonsense_items['total'], 1),
                'commonsense_macro': commonsense_pass_count / total,
                'hard_micro': hard_items['pass'] / max(hard_items['total'], 1),
                'hard_macro': hard_pass_count / total,
                'final_pass_rate': final_pass_count / total,
                'fact_accuracy': avg_fact_accuracy,
                'fact_checked_samples': len(fact_results)
            },
            'counts': {
                'delivery': delivery_count,
                'commonsense_pass': commonsense_pass_count,
                'hard_pass': hard_pass_count,
                'final_pass': final_pass_count,
                'commonsense_items': commonsense_items,
                'hard_items': hard_items
            },
            'detail_results': results,
            'fact_results': fact_results
        }
        
        # 计算总分
        m = summary['metrics']
        if fact_results:
            # 启用事实验证时的权重
            summary['total_score'] = (
                m['delivery_rate'] * 8 +
                m['commonsense_micro'] * 18 +
                m['commonsense_macro'] * 18 +
                m['hard_micro'] * 12 +
                m['hard_macro'] * 12 +
                m['final_pass_rate'] * 17 +
                m['fact_accuracy'] * 15
            )
        else:
            summary['total_score'] = (
                m['delivery_rate'] * 10 +
                m['commonsense_micro'] * 20 +
                m['commonsense_macro'] * 20 +
                m['hard_micro'] * 15 +
                m['hard_macro'] * 15 +
                m['final_pass_rate'] * 20
            )
        
        return summary


def print_results(summary):
    """打印评估结果"""
    print("\n" + "=" * 65)
    print(f"  TravelPlanner 评估结果 - {summary['set_type']}")
    print("=" * 65)
    
    print(f"\n样本数量: {summary['total_samples']}")
    print(f"总分: {summary['total_score']:.2f} / 100")
    
    m = summary['metrics']
    c = summary['counts']
    
    print("\n" + "-" * 65)
    print("  核心指标")
    print("-" * 65)
    print(f"  Delivery Rate:              {m['delivery_rate']*100:.2f}% ({c['delivery']}/{summary['total_samples']})")
    print(f"  Final Pass Rate:            {m['final_pass_rate']*100:.2f}% ({c['final_pass']}/{summary['total_samples']})")
    
    print("\n" + "-" * 65)
    print("  Commonsense Constraint (常识约束)")
    print("-" * 65)
    print(f"  Micro Pass Rate:            {m['commonsense_micro']*100:.2f}%")
    print(f"  Macro Pass Rate:            {m['commonsense_macro']*100:.2f}% ({c['commonsense_pass']}/{summary['total_samples']})")
    
    print("\n" + "-" * 65)
    print("  Hard Constraint (硬约束)")
    print("-" * 65)
    print(f"  Micro Pass Rate:            {m['hard_micro']*100:.2f}%")
    print(f"  Macro Pass Rate:            {m['hard_macro']*100:.2f}% ({c['hard_pass']}/{summary['total_samples']})")
    
    # 事实准确度
    if m.get('fact_checked_samples', 0) > 0:
        print("\n" + "-" * 65)
        print("  Fact Accuracy (事实准确度)")
        print("-" * 65)
        print(f"  Accuracy:                   {m['fact_accuracy']*100:.2f}%")
        print(f"  Checked Samples:            {m['fact_checked_samples']}")
    
    print("\n" + "=" * 65)


def main():
    parser = argparse.ArgumentParser(description='TravelPlanner 简化评测脚本')
    parser.add_argument('--set_type', type=str, default='validation',
                        choices=['train', 'validation', 'test'],
                        help='数据集类型')
    parser.add_argument('--evaluation_file_path', type=str, required=True,
                        help='评测文件路径 (JSONL格式)')
    parser.add_argument('--output_file', type=str, default=None,
                        help='输出结果文件 (可选)')
    
    # 事实验证参数
    parser.add_argument('--enable_fact_check', action='store_true',
                        help='启用事实准确度验证')
    parser.add_argument('--fact_check_samples', type=int, default=5,
                        help='事实验证样本数量 (默认: 5)')
    parser.add_argument('--search_engine', type=str, default='duckduckgo',
                        choices=['serpapi', 'bing', 'duckduckgo'],
                        help='搜索引擎')
    
    args = parser.parse_args()
    
    # 检查文件
    if not os.path.exists(args.evaluation_file_path):
        print(f"错误: 找不到评测文件 {args.evaluation_file_path}")
        sys.exit(1)
    
    # 检查事实验证依赖
    if args.enable_fact_check and not FACT_CHECKER_AVAILABLE:
        print("警告: 事实验证模块不可用")
        args.enable_fact_check = False
    
    # 加载评测数据
    print(f"\n加载评测文件: {args.evaluation_file_path}")
    tested_plans = load_line_json_data(args.evaluation_file_path)
    print(f"加载了 {len(tested_plans)} 条计划")
    
    # 初始化评估器
    evaluator = TravelPlannerEvaluator(
        set_type=args.set_type,
        enable_fact_check=args.enable_fact_check,
        search_engine=args.search_engine
    )
    
    # 加载查询数据
    if not evaluator.load_data():
        print("错误: 无法加载查询数据")
        sys.exit(1)
    
    # 执行评估
    print("\n开始评估...")
    if args.enable_fact_check:
        print(f"[NET] Fact verification enabled (will check first {args.fact_check_samples} samples)")
    
    summary = evaluator.evaluate_batch(tested_plans, fact_check_samples=args.fact_check_samples)
    
    # 打印结果
    print_results(summary)
    
    # 保存结果
    if args.output_file:
        output_data = {
            'set_type': summary['set_type'],
            'total_score': summary['total_score'],
            'metrics': summary['metrics'],
            'counts': summary['counts'],
            'timestamp': datetime.now().isoformat()
        }
        
        with open(args.output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {args.output_file}")
    
    print("\n评估完成!")
    return summary


if __name__ == '__main__':
    main()

