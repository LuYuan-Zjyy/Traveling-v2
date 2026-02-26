"""
路线规划Agent (Route Planning Agent)
================================================================

职责：
  • 接收去重精简后的POI列表和用户约束
  • K-means++ 按地理聚类完成分天（吸收原 app.py 聚类逻辑）
  • 整日景点独占逻辑 + max_full_day 动态上限
  • 地理跨度 → 每日动态容量控制
  • 每天内 TSP 路线优化（2-opt）
  • 生成完整的结构化行程方案
  • 检查约束可行性（预算、时间、距离等）
"""

import json
import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


# ==============================================================
# 数据结构定义
# ==============================================================

class POICategory(Enum):
    """POI类别"""
    ATTRACTION = "attraction"
    RESTAURANT = "restaurant"
    HOTEL = "hotel"
    SHOPPING = "shopping"
    OTHER = "other"


@dataclass
class POI:
    """兴趣点数据结构"""
    id: str
    name: str
    category: str
    latitude: float
    longitude: float
    address: str = ""
    rating: Optional[float] = None
    opening_hours: str = ""
    visit_duration: int = 120      # 建议停留时间(分钟)
    cost: Optional[float] = None
    is_full_day: bool = False      # 是否为整天景点（如主题公园）

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class TimeWindow:
    """时间窗口"""
    start_hour: int
    end_hour: int


@dataclass
class Route:
    """单日行程路线"""
    day: int
    pois: List[POI]
    total_distance: float = 0.0
    total_duration: float = 0.0
    total_cost: float = 0.0
    segments: List[Dict] = None

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
    routes: List[Route]
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
    budget: Optional[float] = None
    daily_budget: Optional[float] = None
    max_daily_distance: float = 50.0
    max_daily_hours: float = 10.0
    start_time: int = 9
    end_time: int = 18
    accommodation_days: int = 1
    prefer_clusters: bool = True
    prefer_varieties: bool = False
    rest_requirement: int = 1


# ==============================================================
# 路线规划Agent
# ==============================================================

class RouteOptimizationAgent:
    """
    路线规划Agent - 地理聚类分天 + 每日 TSP 路线优化

    工作流程：
      1. 解析输入 POI 和约束
      2. 按评分预排序（优质景点优先）
      3. 整日景点按 max_full_day 上限控制，超出则降级为普通景点
      4. K-means++ 按坐标确定每天区域中心
      5. 两轮分配：整日景点独占 → 普通景点按地理跨度动态容量填充
      6. 每天内 2-opt TSP 精排
      7. 就近追加餐厅
      8. 可行性检查
    """

    _FULL_DAY_KEYWORDS = [
        "迪士尼", "环球影城", "游乐园", "主题公园", "野生动物",
        "海洋馆", "水上乐园", "欢乐谷", "方特", "长隆",
        "华侨城", "乐高乐园", "宋城", "横店", "影视城",
        "嘉年华", "动物园", "植物园", "科技馆", "天文台",
    ]

    def __init__(self):
        self.pois: List[POI] = []
        self.distance_matrix: Dict[Tuple[str, str], float] = {}
        self.constraints: UserConstraints = UserConstraints()
        self.duration_days: int = 3

    def plan(self, pois: List[Dict],
             constraints: Dict = None,
             distance_matrix: Optional[Dict] = None,
             restaurants: Optional[List[Dict]] = None) -> Dict:
        """
        主规划接口

        Args:
            pois: POI字典列表
            constraints: 约束 {"budget":5000, "duration_days":3, ...}
            distance_matrix: 预计算距离矩阵（可选）
            restaurants: 餐厅字典列表（可选，就近追加）

        Returns:
            完整规划方案（Dict）
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

        if constraints is None:
            constraints = {}
        self.duration_days = int(constraints.pop("duration_days", 3))

        if constraints:
            self.constraints = UserConstraints(**constraints)

        self.distance_matrix = distance_matrix or self._calculate_distance_matrix()

        print(f"[RouteAgent] {len(self.pois)}个POI，{self.duration_days}天")

        # 2-4. 聚类分天（含评分排序、整日控制、K-means++、动态容量）
        daily_pois = self._cluster_and_split(self.pois, self.duration_days)

        # 5. 每天内 2-opt 精排
        routes = []
        for day, day_poi_list in enumerate(daily_pois, 1):
            if not day_poi_list:
                continue
            optimized = self._optimize_day_route(day_poi_list)
            distance, duration, cost = self._calculate_route_metrics(optimized)
            routes.append(Route(
                day=day,
                pois=optimized,
                total_distance=distance,
                total_duration=duration,
                total_cost=cost,
            ))

        # 6. 就近追加餐厅
        if restaurants:
            used_ids: set = set()
            for route in routes:
                nearby = self._pick_nearby_restaurants(
                    route.pois, restaurants, used_ids, max_count=2
                )
                for rest_dict in nearby:
                    route.pois.append(POI(
                        id=rest_dict["id"],
                        name=rest_dict["name"],
                        category="餐厅",
                        latitude=float(rest_dict.get("latitude", 0)),
                        longitude=float(rest_dict.get("longitude", 0)),
                        rating=rest_dict.get("rating"),
                        cost=rest_dict.get("cost"),
                    ))
                    used_ids.add(rest_dict["id"])

        # 7. 构建 + 可行性检查
        plan = RoutePlan(
            destination="目的地",
            start_date="",
            duration_days=len(routes),
            routes=routes,
        )
        plan = self._check_feasibility(plan)

        print(f"[RouteAgent] 完成: {len(routes)}日, "
              f"总距离{plan.total_distance:.1f}km, 消费{plan.total_cost:.0f}元")
        return plan.to_dict()

    # ==============================================================
    # 分天策略
    # ==============================================================

    def _is_full_day_attraction(self, poi: POI) -> bool:
        """判断是否为整天景点（主题公园、大型自然区等）"""
        if poi.visit_duration >= 360:
            return True
        return any(kw in poi.name for kw in self._FULL_DAY_KEYWORDS)

    # ==============================================================
    # 地理工具函数
    # ==============================================================

    @staticmethod
    def _dist2(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """经纬度平方差（用于快速比较，无需精确距离）"""
        return (lat1 - lat2) ** 2 + (lng1 - lng2) ** 2

    @staticmethod
    def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Haversine 公式计算地表距离（km）"""
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lng2 - lng1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        return 2 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))

    def _kmeans_centers(self, pts: List[Tuple[float, float]], k: int,
                        max_iter: int = 20) -> List[Tuple[float, float]]:
        """K-means++ 聚类，返回 k 个中心坐标。使用时间随机种子，每次结果不同。"""
        import random as _rng_mod, time as _time
        if not pts or k <= 0:
            return []
        if len(pts) <= k:
            return list(pts)

        # 用毫秒时间戳作种子，保证每次规划结果不重复
        rng = _rng_mod.Random(int(_time.time() * 1000))
        centers: List[Tuple[float, float]] = [pts[rng.randint(0, len(pts) - 1)]]
        while len(centers) < k:
            dists = [min(self._dist2(p[0], p[1], c[0], c[1]) for c in centers) for p in pts]
            total = sum(dists)
            if total == 0:
                for p in pts:
                    if p not in centers:
                        centers.append(p)
                        if len(centers) >= k:
                            break
                break
            r = rng.random() * total
            cumul = 0.0
            for i, d in enumerate(dists):
                cumul += d
                if cumul >= r:
                    centers.append(pts[i])
                    break

        for _ in range(max_iter):
            clusters: List[List] = [[] for _ in range(len(centers))]
            for p in pts:
                nearest = min(range(len(centers)),
                              key=lambda i: self._dist2(p[0], p[1], centers[i][0], centers[i][1]))
                clusters[nearest].append(p)
            new_centers = []
            for i, cluster in enumerate(clusters):
                if cluster:
                    new_centers.append((
                        sum(p[0] for p in cluster) / len(cluster),
                        sum(p[1] for p in cluster) / len(cluster),
                    ))
                else:
                    new_centers.append(centers[i])
            if new_centers == centers:
                break
            centers = new_centers
        return centers

    @staticmethod
    def _capacity_for_spread(spread_km: float) -> int:
        """根据当天景点地理跨度决定最多安排几个景点。"""
        if spread_km <= 3:
            return 5   # 步行可达，可多安排
        if spread_km <= 10:
            return 4   # 同区域
        if spread_km <= 25:
            return 3   # 跨区需导航
        return 2       # 远郊/整日景区

    def _day_spread_km(self, day_list: List[POI], new_poi: POI) -> float:
        """将 new_poi 加入 day_list 后，该天所有景点的最大两两距离（km）。"""
        pts = [(p.latitude, p.longitude) for p in day_list]
        pts.append((new_poi.latitude, new_poi.longitude))
        if len(pts) <= 1:
            return 0.0
        max_d = 0.0
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                d = self._haversine_km(pts[i][0], pts[i][1], pts[j][0], pts[j][1])
                if d > max_d:
                    max_d = d
        return max_d

    # ==============================================================
    # 核心：聚类分天
    # ==============================================================

    def _cluster_and_split(self, all_pois: List[POI], num_days: int) -> List[List[POI]]:
        """
        K-means++ 聚类分天（权威版本，取代 app.py 的 _group_attrs_by_cluster）。

        规则：
        - 按评分降序预排序，优先保障高质量景点入选；
        - 整日景点最多 max(1, days//3) 个，超出则降级为普通景点；
        - K-means++ 确定每日区域中心，按地理邻近分配；
        - 每日容量由「地理跨度」动态决定，并不超过 HARD_MAX_PER_DAY=4；
        - 整日景点独占一天（该天对普通景点关闭）；
        - 溢出景点在有空余时补充，无位则丢弃。
        """
        HARD_MAX_PER_DAY = 4
        day_pois: List[List[POI]] = [[] for _ in range(num_days)]

        if not all_pois:
            return day_pois

        # 1. 按评分降序（None 评分视为 0）
        pois = sorted(all_pois, key=lambda p: -(p.rating or 0))

        # 2. 标记整日属性、限制整日景点数量
        max_full_day = max(1, num_days // 3)
        full_day_count = 0
        capped: List[POI] = []
        for poi in pois:
            if self._is_full_day_attraction(poi):
                poi.is_full_day = True
                if full_day_count < max_full_day:
                    capped.append(poi)
                    full_day_count += 1
                else:
                    # 超限：降级为普通景点，保留 visit_duration 但取消整日标志
                    import copy
                    demoted = copy.copy(poi)
                    demoted.is_full_day = False
                    capped.append(demoted)
            else:
                poi.is_full_day = False
                capped.append(poi)
        pois = capped

        # 3. K-means++ 聚类中心（绝对兜底：无中心时顺序均分）
        pts = [(p.latitude, p.longitude) for p in pois]
        centers = self._kmeans_centers(pts, num_days)
        if not centers:
            per = HARD_MAX_PER_DAY
            for idx, poi in enumerate(pois):
                d_i = min(idx // per, num_days - 1)
                if len(day_pois[d_i]) < HARD_MAX_PER_DAY:
                    day_pois[d_i].append(poi)
            return day_pois

        # 长行程（>5天）识别远郊天，让整日景点优先放到远郊天
        long_trip = num_days > 5
        wide_days: set = set()
        if long_trip and len(centers) >= 2:
            g_lat = sum(c[0] for c in centers) / len(centers)
            g_lng = sum(c[1] for c in centers) / len(centers)
            max_c2c = max(
                self._haversine_km(centers[i][0], centers[i][1],
                                   centers[j][0], centers[j][1])
                for i in range(len(centers))
                for j in range(i + 1, len(centers))
            )
            dist_threshold = max_c2c * 0.4
            wide_days = {
                i for i, c in enumerate(centers)
                if self._haversine_km(g_lat, g_lng, c[0], c[1]) > dist_threshold
            }

        counts = [0] * num_days
        full_day_blocked: set = set()
        leftovers: List[POI] = []

        def _assign_one(poi: POI, prefer_wide: bool) -> bool:
            a_lat, a_lng = poi.latitude, poi.longitude

            def _sort_key(i: int) -> tuple:
                zone = 0 if (prefer_wide and i in wide_days) else 1
                dist = self._dist2(a_lat, a_lng, centers[i][0], centers[i][1])
                return (zone, dist)

            for d_i in sorted(range(len(centers)), key=_sort_key):
                if poi.is_full_day:
                    if counts[d_i] == 0 and d_i not in full_day_blocked:
                        day_pois[d_i].append(poi)
                        # 整日景区仍独占全天，但开放1个名额给周边晚间景点/观景台
                        counts[d_i] = HARD_MAX_PER_DAY - 1
                        full_day_blocked.add(d_i)
                        return True
                else:
                    if d_i in full_day_blocked:
                        continue
                    spread = self._day_spread_km(day_pois[d_i], poi)
                    cap = min(self._capacity_for_spread(spread), HARD_MAX_PER_DAY)
                    if counts[d_i] < cap:
                        day_pois[d_i].append(poi)
                        counts[d_i] += 1
                        return True
            return False

        # Pass 1：整日景点优先
        regular: List[POI] = []
        for poi in pois:
            if poi.is_full_day:
                if not _assign_one(poi, prefer_wide=bool(long_trip and wide_days)):
                    leftovers.append(poi)
            else:
                regular.append(poi)

        # Pass 2：普通景点
        for poi in regular:
            if not _assign_one(poi, prefer_wide=False):
                leftovers.append(poi)

        # 溢出：有空余位置则补充，否则丢弃
        for poi in leftovers:
            if poi.is_full_day:
                continue
            candidates = [i for i in range(num_days)
                          if i not in full_day_blocked and counts[i] < HARD_MAX_PER_DAY]
            if not candidates:
                break
            d_i = min(candidates, key=lambda i: counts[i])
            day_pois[d_i].append(poi)
            counts[d_i] += 1

        cap_summary = [f"Day{d+1}={len(day_pois[d])}" for d in range(num_days)]
        print(f"[RouteAgent] 聚类分天: {', '.join(cap_summary)}")
        return day_pois

    def _pick_nearby_restaurants(
        self,
        day_pois: List[POI],
        restaurants: List[Dict],
        used_ids: set,
        max_count: int = 2,
    ) -> List[Dict]:
        """为当天景点选出最近的 max_count 家餐厅（以景点中心为参照）"""
        if not day_pois or not restaurants:
            return []

        center_lat = sum(p.latitude for p in day_pois) / len(day_pois)
        center_lng = sum(p.longitude for p in day_pois) / len(day_pois)

        candidates = []
        for rest in restaurants:
            if rest.get("id") in used_ids:
                continue
            r_lat = float(rest.get("latitude", 0))
            r_lng = float(rest.get("longitude", 0))
            if abs(r_lat) < 1 or abs(r_lng) < 1:
                continue
            dist = self._haversine_km(center_lat, center_lng, r_lat, r_lng)
            candidates.append((dist, rest))

        candidates.sort(key=lambda x: x[0])
        chosen = [r for _, r in candidates[:max_count]]
        if chosen:
            print(f"[RouteAgent] 就近餐厅: {', '.join(r['name'] for r in chosen)}")
        return chosen

    def _calculate_distance_matrix(self) -> Dict[Tuple[str, str], float]:
        """计算所有 POI 对间距离"""
        matrix = {}
        for i, p1 in enumerate(self.pois):
            for j, p2 in enumerate(self.pois):
                if i != j:
                    matrix[(p1.id, p2.id)] = self._haversine_km(
                        p1.latitude, p1.longitude, p2.latitude, p2.longitude
                    )
        return matrix

    def _get_distance(self, poi1_id: str, poi2_id: str) -> float:
        """获取两 POI 间距离；不存在时返回 0"""
        return self.distance_matrix.get((poi1_id, poi2_id), 0.0)

    # ==============================================================
    # 单日路线优化
    # ==============================================================

    def _optimize_day_route(self, pois: List[POI],
                            algorithm: str = "2-opt") -> List[POI]:
        """优化单日路线（默认使用 2-opt）"""
        if len(pois) <= 2:
            return pois
        if algorithm == "greedy":
            return self._greedy_tsp(pois)
        elif algorithm == "2-opt":
            return self._two_opt(self._greedy_tsp(pois))
        elif algorithm == "genetic":
            return self._genetic_tsp(pois)
        return pois

    def _greedy_tsp(self, pois: List[POI]) -> List[POI]:
        """最近邻贪心 TSP"""
        if not pois:
            return []
        unvisited = {p.id for p in pois}
        poi_map = {p.id: p for p in pois}
        current = pois[0]
        route = [current]
        unvisited.remove(current.id)

        while unvisited:
            nearest_id = min(unvisited, key=lambda pid: self._get_distance(current.id, pid))
            current = poi_map[nearest_id]
            route.append(current)
            unvisited.remove(nearest_id)

        return route

    def _two_opt(self, route: List[POI], iterations: int = 100) -> List[POI]:
        """
        2-opt 局部优化（开放路径，无环形绕回）。

        修正原版 bug：`route[j+1 if j+1 < len(route) else 0]` 会将路线
        错误地视为循环路径，导致对开放 TSP 的距离评估不准确。
        修正后：仅当 j+1 < n 时才计算末端边，保持开放路径语义。
        """
        best = route[:]
        n = len(best)
        if n <= 2:
            return best

        improved = True
        it = 0
        while improved and it < iterations:
            improved = False
            it += 1
            for i in range(n - 1):
                for j in range(i + 2, n):
                    # 开放路径：仅当 j+1 < n 时才有从 j 到 j+1 的边
                    d_removed = (
                        self._get_distance(best[i].id, best[i + 1].id)
                        + (self._get_distance(best[j].id, best[j + 1].id) if j + 1 < n else 0.0)
                    )
                    d_added = (
                        self._get_distance(best[i].id, best[j].id)
                        + (self._get_distance(best[i + 1].id, best[j + 1].id) if j + 1 < n else 0.0)
                    )
                    if d_added < d_removed - 1e-9:
                        best[i + 1:j + 1] = best[i + 1:j + 1][::-1]
                        improved = True
        return best

    def _genetic_tsp(self, pois: List[POI],
                     population_size: int = 50,
                     generations: int = 100) -> List[POI]:
        """
        遗传算法 TSP，使用 Order Crossover（OX）。

        修正原版 bug：原版 `child = p1[:n//2] + p2[n//2:]` 会产生包含重复
        POI 且缺少某些 POI 的无效路线。OX 算子通过保留父本 p1 的一段子序列，
        再按 p2 的顺序填充剩余 POI，确保每个 POI 恰好出现一次。
        """
        import random
        n = len(pois)
        if n <= 2:
            return pois

        def fitness(route: List[POI]) -> float:
            total = sum(
                self._get_distance(route[i].id, route[i + 1].id)
                for i in range(len(route) - 1)
            )
            return 1.0 / (1.0 + total)

        def order_crossover(p1: List[POI], p2: List[POI]) -> List[POI]:
            """Order Crossover (OX) — 产生仅含合法排列的子代"""
            a, b = sorted(random.sample(range(n), 2))
            child: List[Optional[POI]] = [None] * n
            # 复制 p1 的 [a, b] 段
            for k in range(a, b + 1):
                child[k] = p1[k]
            # 按 p2 顺序填充剩余位置
            segment_ids = {p.id for p in p1[a:b + 1]}
            remaining = [p for p in p2 if p.id not in segment_ids]
            positions = list(range(b + 1, n)) + list(range(0, a))
            for pos, gene in zip(positions, remaining):
                child[pos] = gene
            return child

        population = [random.sample(pois, n) for _ in range(population_size)]

        for _ in range(generations):
            survivors = sorted(population, key=fitness, reverse=True)[:population_size // 2]
            new_pop = list(survivors)
            while len(new_pop) < population_size:
                p1, p2 = random.choice(survivors), random.choice(survivors)
                child = order_crossover(p1, p2)
                # 变异：随机交换两个位置
                if random.random() < 0.1 and n > 2:
                    i, j = random.sample(range(n), 2)
                    child[i], child[j] = child[j], child[i]
                new_pop.append(child)
            population = new_pop[:population_size]

        return max(population, key=fitness)

    # ==============================================================
    # 约束检查
    # ==============================================================

    def _calculate_route_metrics(self, pois: List[POI]) -> Tuple[float, float, float]:
        """计算路线的总距离（km）、总耗时（h）、总费用（元）"""
        total_distance = 0.0
        total_duration = 0.0
        total_cost = 0.0

        for i in range(len(pois) - 1):
            dist = self._get_distance(pois[i].id, pois[i + 1].id)
            total_distance += dist
            total_duration += dist / 30  # 假设平均 30km/h

        for poi in pois:
            total_duration += poi.visit_duration / 60
            if poi.cost:
                total_cost += poi.cost

        return total_distance, total_duration, total_cost

    def _check_feasibility(self, plan: RoutePlan) -> RoutePlan:
        """检查规划可行性，收集超限警告"""
        warnings = []

        for route in plan.routes:
            if (self.constraints.max_daily_distance
                    and route.total_distance > self.constraints.max_daily_distance):
                warnings.append(
                    f"第{route.day}天距离{route.total_distance:.1f}km > "
                    f"限制{self.constraints.max_daily_distance}km"
                )
            if (self.constraints.max_daily_hours
                    and route.total_duration > self.constraints.max_daily_hours):
                warnings.append(
                    f"第{route.day}天耗时{route.total_duration:.1f}h > "
                    f"限制{self.constraints.max_daily_hours}h"
                )
            if (self.constraints.daily_budget
                    and route.total_cost > self.constraints.daily_budget):
                warnings.append(
                    f"第{route.day}天消费{route.total_cost:.0f}元 > "
                    f"日预算{self.constraints.daily_budget:.0f}元"
                )

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
    pois = [
        {"id": "poi_1", "name": "天柱山", "category": "attraction",
         "latitude": 30.2836, "longitude": 117.0812, "rating": 4.5,
         "visit_duration": 180, "cost": 100},
        {"id": "poi_2", "name": "白崖寨", "category": "attraction",
         "latitude": 30.3200, "longitude": 117.1000, "rating": 4.2,
         "visit_duration": 120, "cost": 50},
        {"id": "poi_3", "name": "黄梅戏博物馆", "category": "attraction",
         "latitude": 30.6500, "longitude": 116.9500, "rating": 4.3,
         "visit_duration": 90, "cost": 30},
    ]
    constraints = {
        "duration_days": 2,
        "max_daily_distance": 50,
        "max_daily_hours": 8,
        "budget": 1000,
    }
    agent = RouteOptimizationAgent()
    plan = agent.plan(pois, constraints)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
