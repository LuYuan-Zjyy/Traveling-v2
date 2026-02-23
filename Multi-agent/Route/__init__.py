"""
Route Planning Agent Package
==========================================

高级路线规划模块，提供TSP求解、聚类、约束检查等功能

导出:
    RouteOptimizationAgent - 路线规划Agent主类
    POI - 兴趣点数据结构
    Route - 单日行程数据结构
    RoutePlan - 完整规划数据结构
    UserConstraints - 用户约束数据结构
"""

from .route_planning_agent import (
    RouteOptimizationAgent,
    POI,
    Route,
    RoutePlan,
    UserConstraints,
    POICategory,
    TimeWindow,
)

__all__ = [
    "RouteOptimizationAgent",
    "POI",
    "Route",
    "RoutePlan",
    "UserConstraints",
    "POICategory",
    "TimeWindow",
]

__version__ = "1.1"
__author__ = "Travel Planning Team"
__description__ = "Advanced Route Planning and Optimization Agent"
