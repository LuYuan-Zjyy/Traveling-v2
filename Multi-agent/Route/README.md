# Route Planning Agent 模块

## 📍 概述

高级旅游路线规划和优化模块，为主Agent (Orchestrator) 提供辅助功能。

## 🏗️ 文件结构

```
Route/
├── __init__.py              # 包初始化，导出公共接口
├── route_planning_agent.py  # 核心实现 (660+行)
└── README.md               # 本文件
```

## 🚀 核心功能

### RouteOptimizationAgent 类

**主要方法**：
- `plan()` - 主规划接口，接收POI列表和约束，返回优化规划
- `_cluster_pois()` - K-means聚类，按地理位置分组
- `_optimize_day_route()` - 单日路线优化（TSP求解）
- `_allocate_to_days()` - 多日分配
- `_check_feasibility()` - 约束检查

**优化算法**：
- Greedy - 贪心/最近邻法
- 2-opt - 局部优化
- Genetic - 遗传算法

### 数据结构

```python
POI              # 兴趣点
Route            # 单日行程
RoutePlan        # 完整规划
UserConstraints  # 用户约束
```

## 💻 使用示例

### 导入
```python
from Route import RouteOptimizationAgent, UserConstraints

# 或完整导入
from Route.route_planning_agent import RouteOptimizationAgent
```

### 基础使用
```python
# 创建Agent
agent = RouteOptimizationAgent()

# 准备数据
pois = [
    {"id": "1", "name": "景点1", "latitude": 30.28, "longitude": 117.08,
     "visit_duration": 120, "cost": 50},
    # ... 更多POI
]

constraints = {
    "duration_days": 3,
    "max_daily_distance": 50,
    "budget": 5000,
}

# 执行规划
plan = agent.plan(pois, constraints)
```

## 📊 性能指标

```
10个POI:   < 100ms
50个POI:   < 200ms
100个POI:  < 500ms
```

## 🔄 与主Agent的集成

在 `orchestrator/orchestrator.py` 中：

```python
from Route import RouteOptimizationAgent

# 在_optimize_route_with_agent方法中使用
optimizer = RouteOptimizationAgent()
optimized_plan = optimizer.plan(pois, constraints)
```

## 📚 详细文档

- 完整设计: 参考 `../README.md` 的路线规划Agent详解
- 算法原理: 参考 `../IMPLEMENTATION_SUMMARY.md`
- 快速参考: 参考 `../QUICK_REFERENCE.md`

## 🛠️ 扩展开发

### 添加新算法

在 `route_planning_agent.py` 中的 `_optimize_day_route` 方法添加新算法：

```python
if algorithm == "your_algorithm":
    return self._your_algorithm(pois)
```

### 自定义约束

扩展 `UserConstraints` 类：

```python
@dataclass
class UserConstraints:
    # ... 现有约束 ...
    new_constraint: bool = False  # 新约束
```

## 📞 常见问题

**Q: 如何选择优化算法?**
A: 
- 快速原型: greedy
- 生产环境: 2-opt
- 高质量离线: genetic

**Q: 支持多少个POI?**
A: 理论上无限制，但>500个建议分批处理

**Q: 如何自定义距离计算?**
A: 修改 `_calculate_distance_matrix()` 调用其他API

## 📈 版本历史

- **v1.1** (2026-02-21) - 首版发布，完整实现5大功能模块

---

**更新时间**: 2026年2月21日  
**维护者**: Travel Planning Team
