#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TripTailor 评测脚本 - 严格版本

评估旅行计划质量的核心指标:
1. 完整性 (Completeness) - 计划是否包含完整信息
2. 沙盒约束 (Within Sandbox) - 是否使用给定范围内的选项
3. 多样性 (Diversity) - 景点/餐厅是否无重复
4. 预算符合 (Within Budget) - 总花费是否在预算内
5. 餐费合理 (Meal Prices) - 餐费是否在指定范围
6. 访问时长 (Visit Duration) - 景点访问时间是否合理
7. 事实准确度 (Fact Accuracy) - 景点/餐厅是否真实存在于正确城市

使用方法:
    python simple_eval.py --input_file <结果文件> --plan_key <模型名_策略>
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from fuzzywuzzy import fuzz
from geopy.distance import geodesic

# 事实验证模块 (可选)
try:
    from fact_checker import FactChecker
    FACT_CHECKER_AVAILABLE = True
except ImportError:
    FACT_CHECKER_AVAILABLE = False


# ============ 严格模糊匹配 ============

def strict_fuzzy_match(target, candidate, ratio_threshold=80, partial_threshold=90):
    """
    严格模糊匹配 - 使用多重验证
    
    Args:
        target: 目标字符串
        candidate: 候选字符串
        ratio_threshold: 完整匹配阈值
        partial_threshold: 部分匹配阈值
    
    Returns:
        (是否匹配, 匹配分数)
    """
    target = target.lower().strip()
    candidate = candidate.lower().strip()
    
    # 完整字符串相似度
    ratio_score = fuzz.ratio(target, candidate)
    # 部分匹配
    partial_score = fuzz.partial_ratio(target, candidate)
    # 词序无关匹配
    token_score = fuzz.token_sort_ratio(target, candidate)
    
    # 加权计算 (ratio 权重最高，防止 partial_ratio 虚假匹配)
    if ratio_score >= 70:
        weighted_score = ratio_score * 0.5 + partial_score * 0.3 + token_score * 0.2
    else:
        weighted_score = ratio_score * 0.7 + token_score * 0.3
    
    # 长度惩罚
    len_ratio = min(len(target), len(candidate)) / max(len(target), len(candidate)) if max(len(target), len(candidate)) > 0 else 0
    if len_ratio < 0.5:
        weighted_score *= len_ratio * 1.5
    
    # 判断是否匹配
    if ratio_score >= ratio_threshold or (partial_score >= partial_threshold and ratio_score >= 60):
        return True, weighted_score
    
    return False, weighted_score


def find_best_match(df, target_name, name_col="name"):
    """在DataFrame中找最佳匹配"""
    if df.empty:
        return False, None
    
    df = df.copy()
    df["_match_result"] = df[name_col].apply(lambda x: strict_fuzzy_match(target_name, str(x))[0])
    df["_match_score"] = df[name_col].apply(lambda x: strict_fuzzy_match(target_name, str(x))[1])
    matched_df = df[df["_match_result"]]
    
    if not matched_df.empty:
        best_idx = matched_df["_match_score"].idxmax()
        return True, matched_df.loc[best_idx]
    return False, None


# ============ 时间解析工具 ============

def parse_time_range(time_str):
    """解析参考时间范围"""
    if pd.isna(time_str) or time_str == '':
        return None
    
    time_pattern = re.compile(
        r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)\s*(hour|minute|day)s?|'
        r'(Over|Under)\s*(\d+\.?\d*)\s*(hour|minute|day)s?|'
        r'(\d+\.?\d*)\s*(hour|minute|day)s?'
    )
    
    match = time_pattern.search(str(time_str))
    if not match:
        return None
    
    if match.group(1) and match.group(2):
        return {"min": float(match.group(1)), "max": float(match.group(2)), "unit": match.group(3)}
    elif match.group(4):
        modifier = match.group(4)
        time_value = float(match.group(5))
        unit = match.group(6)
        if modifier.lower() == "over":
            return {"min": time_value, "max": float("inf"), "unit": unit}
        else:
            return {"min": 0, "max": time_value, "unit": unit}
    elif match.group(7):
        return {"min": float(match.group(7)), "max": float(match.group(7)), "unit": match.group(8)}
    
    return None


def calculate_time_duration(time_range_str):
    """计算时间段的分钟数"""
    time_range_str = str(time_range_str).replace('–', '-')
    
    try:
        parts = time_range_str.split('-')
        if len(parts) != 2:
            return None
        start_time = datetime.strptime(parts[0].strip(), '%H:%M')
        end_time = datetime.strptime(parts[1].strip(), '%H:%M')
        return int((end_time - start_time).total_seconds() / 60)
    except:
        return None


def check_duration(activity_time, reference_time):
    """检查活动时间是否在参考范围内"""
    ref = parse_time_range(reference_time)
    if ref is None:
        return True  # 无参考时间，视为通过
    
    duration = calculate_time_duration(activity_time)
    if duration is None:
        return False
    
    # 转换为分钟
    if ref['unit'] == 'day':
        max_min = ref['max'] * 1440
        min_min = ref['min'] * 1440 / 4 - 60
    elif ref['unit'] == 'hour':
        max_min = ref['max'] * 60 + 60  # 允许1小时误差
        min_min = ref['min'] * 60 - 60
    else:  # minute
        max_min = ref['max'] + 60
        min_min = ref['min']
    
    if max_min == min_min:
        min_min *= 0.5
        max_min *= 1.5
    
    return min_min <= duration <= max_min


# ============ 评估器 ============

class StrictEvaluator:
    """严格评估器"""
    
    def __init__(self, info_file=None, enable_fact_check=False, search_api_key=None, search_engine="duckduckgo"):
        self.given_info = None
        self.fact_checker = None
        
        if info_file and os.path.exists(info_file):
            with open(info_file, 'r', encoding='utf-8') as f:
                self.given_info = json.load(f)
        
        if enable_fact_check and FACT_CHECKER_AVAILABLE:
            self.fact_checker = FactChecker(api_key=search_api_key, search_engine=search_engine)
            print("✅ 事实准确度验证已启用")
    
    def evaluate_single(self, item, plan_key, check_facts=False):
        """评估单个计划"""
        result = {
            'pid': item.get('pid', 'unknown'),
            'completeness': 0.0,
            'sandbox_hotel': False,
            'sandbox_transport': False,
            'sandbox_attraction': False,
            'sandbox_restaurant': False,
            'within_sandbox': False,
            'diverse_attractions': False,
            'diverse_restaurants': False,
            'within_budget': False,
            'reasonable_meal_prices': False,
            'appropriate_duration': True,
            'feasibility': False,
            'rationality': False,
            'fact_accuracy': 1.0,
            'fact_details': None,
            'route_distance': None
        }
        
        plan_json_key = f'{plan_key}_plan_json'
        if plan_json_key not in item:
            return result
        
        try:
            plan = json.loads(item[plan_json_key])
        except:
            return result
        
        # 获取给定信息
        given = None
        if self.given_info and str(item.get('pid', '')) in self.given_info:
            given = self.given_info[str(item['pid'])]
        
        # 1. 完整性检查 (严格)
        result['completeness'] = self._check_completeness_strict(plan)
        
        # 2. 沙盒约束检查 (完整)
        if given:
            sandbox = self._check_sandbox_complete(plan, given)
            result['sandbox_hotel'] = sandbox['hotel']
            result['sandbox_transport'] = sandbox['transport']
            result['sandbox_attraction'] = sandbox['attraction']
            result['sandbox_restaurant'] = sandbox['restaurant']
            result['within_sandbox'] = all(sandbox.values())
        
        # 3. 多样性检查 (严格 - 使用模糊匹配检测重复)
        result['diverse_attractions'] = self._check_diverse_strict(plan, 'sightseeing')
        result['diverse_restaurants'] = self._check_diverse_strict(plan, 'dining')
        
        # 4. 预算检查
        if 'budget' in item and 'day' in item:
            result['within_budget'] = self._check_budget(plan, item['day'], item['budget'])
        
        # 5. 餐费范围检查
        if 'meal_price_range' in item:
            result['reasonable_meal_prices'] = self._check_meal_prices(plan, item['meal_price_range'])
        
        # 6. 访问时长检查
        if given and result['sandbox_attraction']:
            result['appropriate_duration'] = self._check_visit_duration(plan, given)
        
        # 7. 路线距离计算
        if given and result['sandbox_attraction']:
            result['route_distance'] = self._calculate_route_distance(plan, given)
        
        # 8. 事实准确度
        if check_facts and self.fact_checker:
            dest_city = item.get('destination_city', '')
            if dest_city:
                fact_result = self.fact_checker.verify_plan(plan, dest_city, max_checks=5)
                result['fact_accuracy'] = fact_result.get('weighted_accuracy', 1.0)
                result['fact_details'] = fact_result
        
        # 综合指标
        result['feasibility'] = result['completeness'] >= 0.75 and result['within_sandbox']
        result['rationality'] = (
            result['diverse_attractions'] and 
            result['diverse_restaurants'] and 
            result['within_budget'] and 
            result['reasonable_meal_prices'] and
            result['appropriate_duration']
        )
        
        return result
    
    def _check_completeness_strict(self, plan):
        """严格完整性检查"""
        score = 0.0
        total = 5.0  # 增加检查项
        
        # 1. 酒店 (必须有名称和价格)
        if 'hotel' in plan and plan['hotel']:
            hotel = plan['hotel'][0]
            if hotel.get('name') and hotel.get('price_per_night', 0) > 0:
                score += 1.0
        
        # 2. 交通 (必须有2条，且有车次和价格)
        if 'transportation' in plan and len(plan.get('transportation', [])) == 2:
            valid_trans = 0
            for trans in plan['transportation']:
                if trans.get('number') and trans.get('price', 0) > 0:
                    valid_trans += 1
            if valid_trans == 2:
                score += 1.0
        
        # 3. 行程 (必须有内容)
        if 'itinerary' in plan and plan['itinerary']:
            score += 1.0
        
        # 4. 餐饮 (每天至少1餐)
        if 'itinerary' in plan:
            days_with_dining = 0
            for day in plan['itinerary'].values():
                if any(a.get('action') == 'dining' for a in day):
                    days_with_dining += 1
            if days_with_dining >= len(plan['itinerary']):
                score += 1.0
        
        # 5. 景点 (每天至少1个)
        if 'itinerary' in plan:
            days_with_sightseeing = 0
            for day in plan['itinerary'].values():
                if any(a.get('action') == 'sightseeing' for a in day):
                    days_with_sightseeing += 1
            if days_with_sightseeing >= len(plan['itinerary']):
                score += 1.0
        
        return score / total
    
    def _check_sandbox_complete(self, plan, given_info):
        """完整沙盒检查"""
        result = {'hotel': True, 'transport': True, 'attraction': True, 'restaurant': True}
        
        # 1. 酒店检查
        if plan.get('hotel'):
            hotels_df = pd.DataFrame(given_info.get('hotels', []))
            if not hotels_df.empty:
                name_col = 'Hotel Name' if 'Hotel Name' in hotels_df.columns else 'name'
                matched, _ = find_best_match(hotels_df, plan['hotel'][0].get('name', ''), name_col)
                result['hotel'] = matched
        
        # 2. 交通检查 (去程 + 返程)
        trans_list = plan.get('transportation', [])
        if len(trans_list) != 2:
            result['transport'] = False
        else:
            # 去程
            otd_flights = given_info.get('transport_otd', {}).get('flight_options', [])
            otd_trains = given_info.get('transport_otd', {}).get('train_options', [])
            trans = trans_list[0]
            mode = trans.get('mode', '').lower()
            number = trans.get('number', '')
            
            if 'flight' in mode:
                if not any(f.get('Flight Number') == number for f in otd_flights):
                    result['transport'] = False
            elif 'train' in mode:
                if not any(number == t.get('Train_Number') or number in t.get('Train_Number', '').split('/') for t in otd_trains):
                    result['transport'] = False
            else:
                result['transport'] = False
            
            # 返程
            dto_flights = given_info.get('transport_dto', {}).get('flight_options', [])
            dto_trains = given_info.get('transport_dto', {}).get('train_options', [])
            trans = trans_list[1]
            mode = trans.get('mode', '').lower()
            number = trans.get('number', '')
            
            if 'flight' in mode:
                if not any(f.get('Flight Number') == number for f in dto_flights):
                    result['transport'] = False
            elif 'train' in mode:
                if not any(number == t.get('Train_Number') or number in t.get('Train_Number', '').split('/') for t in dto_trains):
                    result['transport'] = False
            else:
                result['transport'] = False
        
        # 3. 景点检查
        attractions_df = pd.DataFrame(given_info.get('attractions', []))
        if not attractions_df.empty and 'itinerary' in plan:
            name_col = 'name_en' if 'name_en' in attractions_df.columns else 'poiName'
            for day in plan['itinerary'].values():
                for activity in day:
                    if activity.get('action') == 'sightseeing':
                        matched, _ = find_best_match(attractions_df, activity.get('location', ''), name_col)
                        if not matched:
                            result['attraction'] = False
                            break
        
        # 4. 餐厅检查
        restaurants_df = pd.DataFrame(given_info.get('restaurants', []))
        if not restaurants_df.empty and 'itinerary' in plan:
            name_col = 'name_en' if 'name_en' in restaurants_df.columns else 'name'
            for day in plan['itinerary'].values():
                for activity in day:
                    if activity.get('action') == 'dining':
                        matched, _ = find_best_match(restaurants_df, activity.get('location', ''), name_col)
                        if not matched:
                            result['restaurant'] = False
                            break
        
        return result
    
    def _check_diverse_strict(self, plan, action_type):
        """严格多样性检查 - 使用模糊匹配检测重复"""
        if 'itinerary' not in plan:
            return False
        
        names = []
        for day in plan['itinerary'].values():
            for activity in day:
                if activity.get('action') == action_type:
                    name = activity.get('location', '').lower().strip()
                    # 检查是否与已有名称相似
                    for existing in names:
                        matched, score = strict_fuzzy_match(name, existing, ratio_threshold=85, partial_threshold=90)
                        if matched:
                            return False  # 发现重复
                    names.append(name)
        
        return len(names) > 0  # 至少有一个
    
    def _check_budget(self, plan, days, budget):
        """预算检查"""
        try:
            cost = 0
            if plan.get('hotel'):
                cost += plan['hotel'][0].get('price_per_night', 0) * (days - 1)
            for trans in plan.get('transportation', []):
                cost += trans.get('price', 0)
            for day in plan.get('itinerary', {}).values():
                for activity in day:
                    cost += activity.get('price', 0)
            return cost <= budget
        except:
            return False
    
    def _check_meal_prices(self, plan, meal_price_range):
        """餐费范围检查"""
        if 'itinerary' not in plan:
            return False
        
        min_price, max_price = meal_price_range
        for day in plan['itinerary'].values():
            for activity in day:
                if activity.get('action') == 'dining':
                    price = activity.get('price', 0)
                    if price < min_price or price > max_price:
                        return False
        return True
    
    def _check_visit_duration(self, plan, given_info):
        """访问时长检查"""
        attractions_df = pd.DataFrame(given_info.get('attractions', []))
        if attractions_df.empty:
            return True
        
        name_col = 'name_en' if 'name_en' in attractions_df.columns else 'poiName'
        time_col = 'recommended_duration' if 'recommended_duration' in attractions_df.columns else 'reference_time'
        
        for day in plan.get('itinerary', {}).values():
            for activity in day:
                if activity.get('action') == 'sightseeing':
                    matched, row = find_best_match(attractions_df, activity.get('location', ''), name_col)
                    if matched and row is not None and time_col in row:
                        if not check_duration(activity.get('time', ''), row[time_col]):
                            return False
        return True
    
    def _calculate_route_distance(self, plan, given_info):
        """计算平均路线距离"""
        try:
            hotels_df = pd.DataFrame(given_info.get('hotels', []))
            attractions_df = pd.DataFrame(given_info.get('attractions', []))
            restaurants_df = pd.DataFrame(given_info.get('restaurants', []))
            
            if hotels_df.empty or not plan.get('hotel'):
                return None
            
            # 获取酒店位置
            hotel_name_col = 'Hotel Name' if 'Hotel Name' in hotels_df.columns else 'name'
            matched, hotel_row = find_best_match(hotels_df, plan['hotel'][0].get('name', ''), hotel_name_col)
            if not matched:
                return None
            
            hotel_point = (float(hotel_row['latitude']), float(hotel_row['longitude']))
            
            attr_name_col = 'name_en' if 'name_en' in attractions_df.columns else 'poiName'
            rest_name_col = 'name_en' if 'name_en' in restaurants_df.columns else 'name'
            
            distances = []
            for day in plan.get('itinerary', {}).values():
                last_point = hotel_point
                for activity in day:
                    point = None
                    if activity.get('action') == 'sightseeing':
                        matched, row = find_best_match(attractions_df, activity.get('location', ''), attr_name_col)
                        if matched and row is not None:
                            point = (float(row['latitude']), float(row['longitude']))
                    elif activity.get('action') == 'dining':
                        matched, row = find_best_match(restaurants_df, activity.get('location', ''), rest_name_col)
                        if matched and row is not None:
                            point = (float(row['latitude']), float(row['longitude']))
                    
                    if point and last_point:
                        distances.append(geodesic(last_point, point).kilometers)
                        last_point = point
                
                if last_point != hotel_point:
                    distances.append(geodesic(last_point, hotel_point).kilometers)
            
            return sum(distances) / len(distances) if distances else None
        except:
            return None
    
    def evaluate_batch(self, data, plan_key, enable_fact_check=False, fact_check_samples=5):
        """批量评估"""
        results = []
        fact_check_count = 0
        
        for i, item in enumerate(data):
            check_facts = enable_fact_check and self.fact_checker and fact_check_count < fact_check_samples
            if check_facts:
                print(f"   🔍 正在验证样本 {item.get('pid', i+1)} 的事实准确度...")
                fact_check_count += 1
            
            result = self.evaluate_single(item, plan_key, check_facts=check_facts)
            results.append(result)
        
        total = len(results)
        if total == 0:
            return {'error': 'No data to evaluate'}
        
        # 事实准确度统计
        fact_checked = [r for r in results if r.get('fact_details') is not None]
        avg_fact = sum(r['fact_accuracy'] for r in fact_checked) / len(fact_checked) if fact_checked else 1.0
        
        # 路线距离统计
        route_distances = [r['route_distance'] for r in results if r['route_distance'] is not None]
        avg_route = sum(route_distances) / len(route_distances) if route_distances else None
        
        summary = {
            'total_samples': total,
            'metrics': {
                'completeness': sum(r['completeness'] for r in results) / total * 100,
                'sandbox_hotel': sum(r['sandbox_hotel'] for r in results) / total * 100,
                'sandbox_transport': sum(r['sandbox_transport'] for r in results) / total * 100,
                'sandbox_attraction': sum(r['sandbox_attraction'] for r in results) / total * 100,
                'sandbox_restaurant': sum(r['sandbox_restaurant'] for r in results) / total * 100,
                'within_sandbox': sum(r['within_sandbox'] for r in results) / total * 100,
                'diverse_attractions': sum(r['diverse_attractions'] for r in results) / total * 100,
                'diverse_restaurants': sum(r['diverse_restaurants'] for r in results) / total * 100,
                'within_budget': sum(r['within_budget'] for r in results) / total * 100,
                'reasonable_meal_prices': sum(r['reasonable_meal_prices'] for r in results) / total * 100,
                'appropriate_duration': sum(r['appropriate_duration'] for r in results) / total * 100,
                'feasibility': sum(r['feasibility'] for r in results) / total * 100,
                'rationality': sum(r['rationality'] for r in results) / total * 100,
                'fact_accuracy': avg_fact * 100,
                'fact_checked_samples': len(fact_checked),
                'avg_route_distance': avg_route
            },
            'detail_results': results
        }
        
        # 计算总分
        m = summary['metrics']
        if enable_fact_check and fact_checked:
            summary['total_score'] = (
                m['completeness'] * 0.15 +
                m['within_sandbox'] * 0.15 +
                m['diverse_attractions'] * 0.08 +
                m['diverse_restaurants'] * 0.08 +
                m['within_budget'] * 0.12 +
                m['reasonable_meal_prices'] * 0.08 +
                m['appropriate_duration'] * 0.08 +
                m['feasibility'] * 0.03 +
                m['rationality'] * 0.03 +
                m['fact_accuracy'] * 0.20
            )
        else:
            summary['total_score'] = (
                m['completeness'] * 0.20 +
                m['within_sandbox'] * 0.18 +
                m['diverse_attractions'] * 0.10 +
                m['diverse_restaurants'] * 0.10 +
                m['within_budget'] * 0.15 +
                m['reasonable_meal_prices'] * 0.10 +
                m['appropriate_duration'] * 0.10 +
                m['feasibility'] * 0.035 +
                m['rationality'] * 0.035
            )
        
        return summary


def print_results(summary, plan_key):
    """打印评估结果"""
    print("\n" + "=" * 65)
    print(f"  评估结果 - {plan_key}")
    print("=" * 65)
    
    print(f"\n📊 样本数量: {summary['total_samples']}")
    print(f"📈 总分: {summary['total_score']:.2f} / 100")
    
    m = summary['metrics']
    
    print("\n" + "-" * 65)
    print("  基础指标")
    print("-" * 65)
    print(f"  完整性 (Completeness):          {m['completeness']:.2f}%")
    print(f"  预算符合 (Within Budget):       {m['within_budget']:.2f}%")
    print(f"  餐费合理 (Meal Prices):         {m['reasonable_meal_prices']:.2f}%")
    
    print("\n" + "-" * 65)
    print("  沙盒约束 (详细)")
    print("-" * 65)
    print(f"  酒店约束:                       {m['sandbox_hotel']:.2f}%")
    print(f"  交通约束:                       {m['sandbox_transport']:.2f}%")
    print(f"  景点约束:                       {m['sandbox_attraction']:.2f}%")
    print(f"  餐厅约束:                       {m['sandbox_restaurant']:.2f}%")
    print(f"  总体沙盒 (Within Sandbox):      {m['within_sandbox']:.2f}%")
    
    print("\n" + "-" * 65)
    print("  多样性与时长")
    print("-" * 65)
    print(f"  景点多样性:                     {m['diverse_attractions']:.2f}%")
    print(f"  餐厅多样性:                     {m['diverse_restaurants']:.2f}%")
    print(f"  访问时长合理:                   {m['appropriate_duration']:.2f}%")
    
    print("\n" + "-" * 65)
    print("  综合指标")
    print("-" * 65)
    print(f"  可行性 (Feasibility):           {m['feasibility']:.2f}%")
    print(f"  合理性 (Rationality):           {m['rationality']:.2f}%")
    
    if m.get('avg_route_distance') is not None:
        print(f"  平均路线距离:                   {m['avg_route_distance']:.2f} km")
    
    if m.get('fact_checked_samples', 0) > 0:
        print(f"\n🌐 事实准确度:                    {m['fact_accuracy']:.2f}%")
        print(f"   (已验证 {m['fact_checked_samples']} 个样本)")
    
    print("\n" + "=" * 65)


def main():
    parser = argparse.ArgumentParser(description='TripTailor 评测脚本 - 严格版本')
    
    parser.add_argument('--input_file', type=str, required=True, help='输入文件路径')
    parser.add_argument('--plan_key', type=str, required=True, help='计划键名')
    parser.add_argument('--info_file', type=str, default='../../data/infomation.json', help='给定信息文件')
    parser.add_argument('--output_file', type=str, default=None, help='输出结果文件')
    parser.add_argument('--detail', action='store_true', help='输出详细结果')
    
    # 事实验证
    parser.add_argument('--enable_fact_check', action='store_true', help='启用事实验证')
    parser.add_argument('--search_engine', type=str, default='duckduckgo', 
                        choices=['serpapi', 'bing', 'google', 'duckduckgo'])
    parser.add_argument('--search_api_key', type=str, default=None)
    parser.add_argument('--fact_check_samples', type=int, default=5)
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        print(f"❌ 错误: 找不到输入文件 {args.input_file}")
        sys.exit(1)
    
    print(f"\n📁 加载数据: {args.input_file}")
    with open(args.input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"📊 数据条数: {len(data)}")
    
    if args.enable_fact_check and not FACT_CHECKER_AVAILABLE:
        print("⚠️ 事实验证模块不可用")
        args.enable_fact_check = False
    
    evaluator = StrictEvaluator(
        info_file=args.info_file if os.path.exists(args.info_file) else None,
        enable_fact_check=args.enable_fact_check,
        search_api_key=args.search_api_key,
        search_engine=args.search_engine
    )
    
    print(f"\n⏳ 正在评估...")
    summary = evaluator.evaluate_batch(
        data, args.plan_key,
        enable_fact_check=args.enable_fact_check,
        fact_check_samples=args.fact_check_samples
    )
    
    print_results(summary, args.plan_key)
    
    if args.output_file:
        output_data = {
            'plan_key': args.plan_key,
            'total_score': summary['total_score'],
            'total_samples': summary['total_samples'],
            'metrics': summary['metrics'],
            'timestamp': datetime.now().isoformat()
        }
        if args.detail:
            output_data['detail_results'] = summary['detail_results']
        
        with open(args.output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\n💾 结果已保存到: {args.output_file}")
    
    print("\n✅ 评估完成!\n")
    return summary


if __name__ == '__main__':
    main()
