"""
路线规划Agent (Route Planning Agent)
================================================================

职责：
  • 接收主Agent提取的POI列表和用户约束
  • 分析POI之间的距离关系，进行聚类和分组
  • 使用高级算法（TSP、贪心、遗传算法）优化访问顺序
  • 生成可执行的详细行程方案
  • 检查约束可行性（预算、时间、距离等）

核心功能：
  1. POI聚类 - 按地理位置分组相近景点
  2. 路线优化 - TSP问题求解
  3. 可行性检查 - 时间预算约束验证
  4. 多方案生成 - 提供不同风格的规划方案
"""

import json
import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import heapq


# ==============================================================
# 数据结构定义
# ==============================================================

class POICategory(Enum):
    """POI类别"""
    ATTRACTION = "attraction"      # 景点
    RESTAURANT = "restaurant"      # 餐厅
    HOTEL = "hotel"               # 酒店
    SHOPPING = "shopping"         # 购物
    OTHER = "other"


@dataclass
class POI:
    """兴趣点数据结构"""
    id: str
    name: str
    category: str                  # POI类别
    latitude: float
    longitude: float
    address: str = ""
    rating: Optional[float] = None
    opening_hours: str = ""
    visit_duration: int = 120      # 建议停留时间(分钟)
    cost: Optional[float] = None   # 消费金额
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TimeWindow:
    """时间窗口(用于景点开闭时间约束)"""
    start_hour: int                # 营业开始小时
    end_hour: int                  # 营业结束小时


@dataclass
class Route:
    """单日行程路线"""
    day: int
    pois: List[POI]                # 该日访问的POI顺序
    total_distance: float = 0.0    # 总距离(km)
    total_duration: float = 0.0    # 总耗时(小时，含停留)
    total_cost: float = 0.0        # 总消费
    segments: List[Dict] = None    # 段间信息(距离、耗时、交通方式)
    
    def __post_init__(self):
        if self.segments is None:
            self.segments = []
    
    def to_dict(self) -> Dict:
        return {
            "day": self.day,
            "pois": [poi.to_dict() for poi in self.pois],
            "total_distance": self.total_distance,
            "total_duration": self.total_duration,
            "total_cost": self.total_cost,
            "segments": self.segments,
        }


@dataclass
class RoutePlan:
    """完整行程规划"""
    destination: str
    start_date: str
    duration_days: int
    routes: List[Route]            # 每日路线
    total_distance: float = 0.0
    total_cost: float = 0.0
    feasibility: bool = True
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    def to_dict(self) -> Dict:
        return {
            "destination": self.destination,
            "start_date": self.start_date,
            "duration_days": self.duration_days,
            "routes": [r.to_dict() for r in self.routes],
            "total_distance": self.total_distance,
            "total_cost": self.total_cost,
            "feasibility": self.feasibility,
            "warnings": self.warnings,
        }


@dataclass
class UserConstraints:
    """用户约束条件"""
    budget: Optional[float] = None          # 总预算
    daily_budget: Optional[float] = None    # 日均预算
    max_daily_distance: float = 50.0        # 每日最大距离(km)
    max_daily_hours: float = 10.0           # 每日活动时间(小时)
    start_time: int = 9                     # 每日出发时间(小时)
    end_time: int = 18                      # 每日返回时间(小时)
    accommodation_days: int = 1             # 同一酒店停留天数(天)
    prefer_clusters: bool = True            # 偏好按地理位置聚集
    prefer_varieties: bool = False          # 偏好多样化(各类型POI混合)
    rest_requirement: int = 1               # 所需休息天数
    

# ==============================================================
# 路线规划Agent
# ==============================================================

class RouteOptimizationAgent:
    """
    路线规划Agent - 高级路线优化和行程规划
    
    工作流程：
      1. 接收主Agent提供的POI列表和约束
      2. POI聚类 - 按地理位置和类型聚集
      3. 路线优化 - 在每个聚类内部应用TSP求解
      4. 多日分配 - 将POI分配到不同天次
      5. 可行性检查 - 验证约束满足情况
      6. 方案生成 - 输出详细行程
    """
    
    def __init__(self):
        self.pois: List[POI] = []
        self.distance_matrix: Dict[Tuple[str, str], float] = {}
        self.constraints: UserConstraints = UserConstraints()
    
    def plan(self, pois: List[Dict], 
             constraints: Dict = None,
             distance_matrix: Optional[Dict] = None) -> Dict:
        """
        主规划接口
        
        Args:
            pois: POI列表 [{"id":"...", "name":"...", "latitude":..., "longitude":..., ...}, ...]
            constraints: 用户约束 {"budget": 5000, "duration_days": 3, ...}
            distance_matrix: 距离矩阵 {("id1", "id2"): 12.5, ...}
        
        Returns:
            完整规划方案 (Dict格式)
        """
        # 1. 解析输入
        self.pois = [POI(
            id=p.get("id", f"poi_{i}"),
            name=p.get("name", ""),
            category=p.get("category", "attraction"),
            latitude=float(p.get("latitude", 0)),
            longitude=float(p.get("longitude", 0)),
            address=p.get("address", ""),
            rating=p.get("rating"),
            opening_hours=p.get("opening_hours", ""),
            visit_duration=p.get("visit_duration", 120),
            cost=p.get("cost"),
        ) for i, p in enumerate(pois)]
        
        # ✅ 从 constraints 中提取 duration_days（如果有）
        if constraints is None:
            constraints = {}
        self.duration_days = constraints.pop("duration_days", 3)  # 默认3天
        
        if constraints:
            self.constraints = UserConstraints(**constraints)
        
        self.distance_matrix = distance_matrix or self._calculate_distance_matrix()
        
        print(f"[RouteAgent] 收到{len(self.pois)}个POI，约束: {self.constraints}，规划天数: {self.duration_days}天")
        
        # 2. 聚类
        clusters = self._cluster_pois()
        print(f"[RouteAgent] POI聚类完成: {len(clusters)}个聚类")
        
        # 3. 多日分配
        daily_pois = self._allocate_to_days(clusters)
        print(f"[RouteAgent] 多日分配完成")
        
        # 4. 每日路线优化
        routes = []
        for day, day_poi_list in enumerate(daily_pois, 1):
            if day_poi_list:
                optimized_pois = self._optimize_day_route(day_poi_list)
                distance, duration, cost = self._calculate_route_metrics(optimized_pois)
                
                route = Route(
                    day=day,
                    pois=optimized_pois,
                    total_distance=distance,
                    total_duration=duration,
                    total_cost=cost,
                )
                routes.append(route)
        
        # 5. 构建完整规划
        plan = RoutePlan(
            destination="目的地",
            start_date="",
            duration_days=len(daily_pois),
            routes=routes,
        )
        
        # 6. 可行性检查
        plan = self._check_feasibility(plan)
        
        print(f"[RouteAgent] 规划完成: {len(routes)}日行程，"
              f"总距离{plan.total_distance:.1f}km, 总消费{plan.total_cost:.0f}元")
        
        return plan.to_dict()
    
    # ==============================================================
    # 距离计算
    # ==============================================================
    
    def _haversine_distance(self, lat1: float, lon1: float, 
                           lat2: float, lon2: float) -> float:
        """
        使用Haversine公式计算两点间的地球表面距离
        
        Returns:
            距离(km)
        """
        R = 6371  # 地球半径(km)
        
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        return R * c
    
    def _calculate_distance_matrix(self) -> Dict[Tuple[str, str], float]:
        """计算所有POI对间的距离"""
        matrix = {}
        for i, poi1 in enumerate(self.pois):
            for j, poi2 in enumerate(self.pois):
                if i != j:
                    dist = self._haversine_distance(
                        poi1.latitude, poi1.longitude,
                        poi2.latitude, poi2.longitude
                    )
                    matrix[(poi1.id, poi2.id)] = dist
        return matrix
    
    def _get_distance(self, poi1_id: str, poi2_id: str) -> float:
        """获取两个POI间的距离"""
        if (poi1_id, poi2_id) in self.distance_matrix:
            return self.distance_matrix[(poi1_id, poi2_id)]
        return 0.0
    
    # ==============================================================
    # POI聚类 - K-means变种
    # ==============================================================
    
    def _cluster_pois(self, max_clusters: int = 5) -> List[List[POI]]:
        """
        使用简化的K-means进行地理聚类
        
        Returns:
            聚类结果 [[POI1, POI2, ...], ...]
        """
        if len(self.pois) <= 3:
            return [self.pois]
        
        # 确定聚类数
        k = min(max_clusters, max(1, len(self.pois) // 3))
        
        # 初始化质心(使用最分散的点)
        centers = self._init_centers(k)
        
        # K-means迭代
        for iteration in range(10):
            # 分配点到最近质心
            clusters = [[] for _ in range(k)]
            for poi in self.pois:
                closest_center = min(range(k), 
                    key=lambda i: self._haversine_distance(
                        poi.latitude, poi.longitude,
                        centers[i][0], centers[i][1]
                    ))
                clusters[closest_center].append(poi)
            
            # 更新质心
            new_centers = []
            for cluster in clusters:
                if cluster:
                    avg_lat = sum(p.latitude for p in cluster) / len(cluster)
                    avg_lon = sum(p.longitude for p in cluster) / len(cluster)
                    new_centers.append((avg_lat, avg_lon))
                else:
                    new_centers.append(centers[len(new_centers)])
            
            centers = new_centers
        
        # 过滤空聚类
        return [c for c in clusters if c]
    
    def _init_centers(self, k: int) -> List[Tuple[float, float]]:
        """使用k-means++初始化质心"""
        centers = [
            (self.pois[0].latitude, self.pois[0].longitude)
        ]
        
        for _ in range(k - 1):
            # 计算每个点到最近质心的距离
            distances = []
            for poi in self.pois:
                min_dist = min(
                    self._haversine_distance(poi.latitude, poi.longitude, c[0], c[1])
                    for c in centers
                )
                distances.append(min_dist ** 2)
            
            # 按距离概率选择新质心
            total_dist = sum(distances)
            if total_dist > 0:
                probabilities = [d / total_dist for d in distances]
                idx = self._weighted_choice(probabilities)
                centers.append((self.pois[idx].latitude, self.pois[idx].longitude))
            else:
                # 随机选择
                import random
                idx = random.randint(0, len(self.pois) - 1)
                centers.append((self.pois[idx].latitude, self.pois[idx].longitude))
        
        return centers
    
    @staticmethod
    def _weighted_choice(weights: List[float]) -> int:
        """根据权重选择索引"""
        import random
        r = random.random() * sum(weights)
        s = 0
        for i, w in enumerate(weights):
            s += w
            if r <= s:
                return i
        return len(weights) - 1
    
    # ==============================================================
    # 多日分配
    # ==============================================================
    
    def _allocate_to_days(self, clusters: List[List[POI]]) -> List[List[POI]]:
        """
        将聚类POI分配到不同天数
        
        Returns:
            按天分组的POI列表 [[day1_pois], [day2_pois], ...]
        """
        num_days = self.duration_days  # ✅ 使用实例变量 duration_days
        daily_pois = [[] for _ in range(num_days)]
        
        # 简单策略：轮流分配聚类到不同天
        for day_idx, cluster in enumerate(clusters):
            assigned_day = day_idx % num_days
            daily_pois[assigned_day].extend(cluster)
        
        return daily_pois
    
    # ==============================================================
    # 单日路线优化
    # ==============================================================
    
    def _optimize_day_route(self, pois: List[POI], 
                           algorithm: str = "greedy") -> List[POI]:
        """
        优化单日路线(TSP问题求解)
        
        Args:
            pois: 该日的POI列表
            algorithm: 优化算法 ["greedy", "2-opt", "genetic"]
        
        Returns:
            优化后的POI访问顺序
        """
        if len(pois) <= 2:
            return pois
        
        if algorithm == "greedy":
            return self._greedy_tsp(pois)
        elif algorithm == "2-opt":
            initial = self._greedy_tsp(pois)
            return self._two_opt(initial)
        elif algorithm == "genetic":
            return self._genetic_tsp(pois)
        else:
            return pois
    
    def _greedy_tsp(self, pois: List[POI]) -> List[POI]:
        """贪心算法求解TSP - 最近邻法"""
        if not pois:
            return []
        
        unvisited = set(p.id for p in pois)
        current = pois[0]
        route = [current]
        unvisited.remove(current.id)
        
        while unvisited:
            nearest = min(
                unvisited,
                key=lambda poi_id: self._get_distance(current.id, poi_id)
            )
            nearest_poi = next(p for p in pois if p.id == nearest)
            route.append(nearest_poi)
            current = nearest_poi
            unvisited.remove(nearest)
        
        return route
    
    def _two_opt(self, route: List[POI], iterations: int = 100) -> List[POI]:
        """2-opt局部优化"""
        best_route = route[:]
        improved = True
        iteration = 0
        
        while improved and iteration < iterations:
            improved = False
            iteration += 1
            
            for i in range(1, len(route) - 2):
                for j in range(i + 1, len(route)):
                    # 计算交换前后的距离
                    before = (
                        self._get_distance(route[i-1].id, route[i].id) +
                        self._get_distance(route[j].id, route[j+1 if j+1 < len(route) else 0].id)
                    )
                    
                    after = (
                        self._get_distance(route[i-1].id, route[j].id) +
                        self._get_distance(route[i].id, route[j+1 if j+1 < len(route) else 0].id)
                    )
                    
                    if after < before:
                        # 执行交换
                        best_route[i:j+1] = reversed(best_route[i:j+1])
                        improved = True
                        break
                
                if improved:
                    break
        
        return best_route
    
    def _genetic_tsp(self, pois: List[POI], 
                    population_size: int = 50, 
                    generations: int = 100) -> List[POI]:
        """遗传算法求解TSP"""
        import random
        
        def fitness(route):
            distance = sum(
                self._get_distance(route[i].id, route[(i+1) % len(route)].id)
                for i in range(len(route))
            )
            return 1 / (1 + distance)  # 适应度函数
        
        # 初始种群
        population = [pois[::] for _ in range(population_size)]
        for ind in population:
            random.shuffle(ind)
        
        for gen in range(generations):
            # 评估
            fitness_scores = [fitness(ind) for ind in population]
            
            # 选择
            population = sorted(
                zip(population, fitness_scores),
                key=lambda x: x[1],
                reverse=True
            )[:population_size // 2]
            population = [ind for ind, _ in population]
            
            # 交叉和变异
            new_population = population[:]
            while len(new_population) < population_size:
                # 随机选择两个父代
                p1 = random.choice(population)
                p2 = random.choice(population)
                
                # 交叉
                child = p1[:len(p1)//2] + p2[len(p1)//2:]
                
                # 变异
                if random.random() < 0.1:
                    i, j = random.sample(range(len(child)), 2)
                    child[i], child[j] = child[j], child[i]
                
                new_population.append(child)
            
            population = new_population[:population_size]
        
        # 返回最优个体
        return max(population, key=fitness)
    
    # ==============================================================
    # 约束检查
    # ==============================================================
    
    def _calculate_route_metrics(self, pois: List[POI]) -> Tuple[float, float, float]:
        """
        计算路线的距离、时间和成本
        
        Returns:
            (总距离km, 总耗时小时, 总成本元)
        """
        total_distance = 0.0
        total_duration = 0.0
        total_cost = 0.0
        
        # 距离和耗时
        for i in range(len(pois) - 1):
            dist = self._get_distance(pois[i].id, pois[i+1].id)
            total_distance += dist
            # 假设平均速度30km/h
            total_duration += dist / 30
        
        # 停留时间
        for poi in pois:
            total_duration += poi.visit_duration / 60
        
        # 成本
        for poi in pois:
            if poi.cost:
                total_cost += poi.cost
        
        return total_distance, total_duration, total_cost
    
    def _check_feasibility(self, plan: RoutePlan) -> RoutePlan:
        """检查规划的可行性"""
        warnings = []
        
        for route in plan.routes:
            # 检查每日距离
            if self.constraints.max_daily_distance:
                if route.total_distance > self.constraints.max_daily_distance:
                    warnings.append(
                        f"第{route.day}天距离{route.total_distance:.1f}km > "
                        f"限制{self.constraints.max_daily_distance}km"
                    )
            
            # 检查每日时间
            if self.constraints.max_daily_hours:
                if route.total_duration > self.constraints.max_daily_hours:
                    warnings.append(
                        f"第{route.day}天耗时{route.total_duration:.1f}h > "
                        f"限制{self.constraints.max_daily_hours}h"
                    )
            
            # 检查每日预算
            if self.constraints.daily_budget:
                if route.total_cost > self.constraints.daily_budget:
                    warnings.append(
                        f"第{route.day}天消费{route.total_cost:.0f}元 > "
                        f"日预算{self.constraints.daily_budget:.0f}元"
                    )
        
        # 检查总预算
        total_cost = sum(r.total_cost for r in plan.routes)
        if self.constraints.budget and total_cost > self.constraints.budget:
            warnings.append(
                f"总消费{total_cost:.0f}元 > 总预算{self.constraints.budget:.0f}元"
            )
        
        plan.warnings = warnings
        plan.feasibility = len(warnings) == 0
        plan.total_distance = sum(r.total_distance for r in plan.routes)
        plan.total_cost = sum(r.total_cost for r in plan.routes)
        
        return plan


# ==============================================================
# 使用示例
# ==============================================================

if __name__ == "__main__":
    # 示例POI数据
    pois = [
        {
            "id": "poi_1",
            "name": "天柱山",
            "category": "attraction",
            "latitude": 30.2836,
            "longitude": 117.0812,
            "address": "安庆市潜山市",
            "rating": 4.5,
            "visit_duration": 180,
            "cost": 100,
        },
        {
            "id": "poi_2",
            "name": "白崖寨",
            "category": "attraction",
            "latitude": 30.3200,
            "longitude": 117.1000,
            "address": "安庆市潜山市",
            "rating": 4.2,
            "visit_duration": 120,
            "cost": 50,
        },
        {
            "id": "poi_3",
            "name": "黄梅戏博物馆",
            "category": "attraction",
            "latitude": 30.6500,
            "longitude": 116.9500,
            "address": "安庆市迎江区",
            "rating": 4.3,
            "visit_duration": 90,
            "cost": 30,
        },
    ]
    
    constraints = {
        "duration_days": 2,
        "max_daily_distance": 50,
        "max_daily_hours": 8,
        "budget": 1000,
    }
    
    agent = RouteOptimizationAgent()
    plan = agent.plan(pois, constraints)
    
    print("\n=== 规划结果 ===")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
