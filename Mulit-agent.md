# Traveling-v2 多Agent协作框架设计文档

## 🎯 系统概览

### 目标
构建一个**分层分工**的AI旅游规划系统，通过多个专业Agent的协作，为用户生成**文化丰富、成本合理、体验流畅**的个性化旅行方案。

### 系统总体流程

```
┌─────────────────┐
│   用户输入      │  "我想去安庆3天，体验黄梅戏和乡村文化，预算5000"
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  🎯 主控Agent (Orchestrator)            │
│  • 意图识别                              │
│  • 任务分解                              │
│  • Agent调度                             │
│  • 冲突解决                              │
│  • 结果融合                              │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  🤖 专业Agent层 (并行/顺序执行)                                 │
│                                                                   │
│  [1] 数据采集Agent ──→ 高德API、外部API                          │
│       └─ POI列表、天气、价格、交通信息                            │
│                                                                   │
│  [2] 文化体验Agent ──→ 文化资源匹配                              │
│       └─ 文化景点、活动、背景说明                                │
│                                                                   │
│  [3] 路由优化Agent ──→ TSP、遗传算法                             │
│       └─ 优化路线、停留时间、交通方式                            │
│                                                                   │
│  [4] 费用规划Agent ──→ 成本估算、预算分配                        │
│       └─ 费用清单、预算优化、超支预警                            │
│                                                                   │
│  [5] 运营优化Agent ──→ 时间优化、应急策略                        │
│       └─ 最终行程表、休息安排、备选方案                          │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────┐
│  📤 输出结果         │
│  • 完整行程方案      │
│  • 交互式地图        │
│  • 结构化报告        │
└─────────────────────┘
```

---

## 🏗️ 架构设计

### 第一层：主控层 (Orchestrator)

**现状**：✅ 已实现  
**位置**：`orchestrator/orchestrator.py`

**核心职责**：
1. **意图识别** - 解析用户输入，提取旅行参数
   - 目的地、日期、预算、人数
   - 用户偏好（文化、美食、户外等）
   - 住宿和交通偏好

2. **任务分解** - 确定调用哪些Agent和工具
   - 根据用户需求制定执行计划
   - 指定Agent的执行顺序和依赖关系

3. **Agent调度** - 控制执行流程
   - 启动必要的Agent
   - 管理执行顺序（串联/并行）
   - 收集每个Agent的输出

4. **冲突解决** - 处理Agent之间的矛盾需求
   - 费用超预算 ↔ 体验质量
   - 时间紧张 ↔ 景点众多
   - 文化偏好 ↔ 通用景点

5. **结果融合** - 整合多个Agent的结果
   - 生成最终行程方案
   - 输出结构化数据供Web前端使用

---

### 第二层：专业Agent层

#### **1. 数据采集Agent** 🆕

**职责**：获取和整理规划所需的基础数据

**输入**：
- 目的地信息（城市、坐标）
- 需要采集的数据类型（景点、餐厅、酒店、天气等）
- 搜索过滤条件（半径、数量限制等）

**核心功能**：

| 功能 | 说明 | 数据源 |
|-----|------|--------|
| **POI搜索** | 搜索景点、餐厅、酒店 | 高德地图API |
| **周边搜索** | 查询景点周边的配套设施 | 高德地图API |
| **天气查询** | 获取目的地天气预报 | 高德天气API |
| **路线查询** | 获取两点间的行驶时间和距离 | 高德地图API |
| **详细信息** | 景点评分、营业时间、门票价格 | 外部API/缓存库 |

**输出**：
```json
{
  "pois": [
    {
      "id": "poi_001",
      "name": "黄梅戏博物馆",
      "category": "景点",
      "location": {"lat": 30.65, "lng": 117.05},
      "rating": 4.8,
      "ticket_price": 60,
      "opening_hours": "09:00-17:00",
      "description": "..."
    }
  ],
  "weather": {
    "date": "2026-03-01",
    "high": 25,
    "low": 15,
    "weather": "晴"
  },
  "routes": [
    {
      "from": "poi_001",
      "to": "poi_002",
      "duration_minutes": 45,
      "distance_km": 23.5
    }
  ]
}
```

**数据缓存策略**：
- 城市基础数据：7天过期
- 天气数据：1天过期
- POI详情：30天过期
- 路线数据：实时查询（或1天缓存）

---

#### **2. 文化体验Agent** 🆕 【关键Agent】

**职责**：为用户打造**有灵魂的旅行体验**

**核心理念**：
> 不是简单地列出景点，而是讲好每个地方的故事，让旅行变成文化之旅。

**输入**：
- 用户文化偏好（来自意图识别）
- 目的地所有POI列表（来自数据采集Agent）
- 旅行天数和时间安排

**核心功能**：

| 功能 | 输出 | 例子 |
|-----|------|------|
| **文化主题识别** | 匹配目的地特色和用户偏好 | "黄梅戏"、"乡村民俗" |
| **资源匹配** | 筛选和排序最符合的文化景点 | 黄梅戏博物馆 > 戏曲传承基地 |
| **活动规划** | 推荐文化活动和特色体验 | 19:00黄梅戏表演、农家篝火 |
| **背景生成** | 为景点编写文化说明和故事 | "千年黄梅戏，一代又一代..." |
| **体验设计** | 创意组合（如"沉浸式非遗体验"） | 戏曲学习 → 演员互动 → 大戏欣赏 |

**输出**：
```json
{
  "cultural_theme": "黄梅戏非遗文化 + 江南乡村体验",
  "cultural_pois": [
    {
      "poi_id": "poi_001",
      "name": "黄梅戏博物馆",
      "priority": 1,
      "reason": "黄梅戏的发源地和传承中心",
      "cultural_background": "黄梅戏起源于安庆地区，被誉为'中国第五大戏曲'...",
      "recommended_duration": 90,
      "related_activities": [
        {
          "activity": "黄梅戏表演欣赏",
          "time": "19:00-20:30",
          "cost": 200,
          "description": "观看专业演员的精彩表演"
        }
      ]
    }
  ],
  "special_experiences": [
    {
      "name": "沉浸式戏曲体验",
      "description": "与戏曲演员互动，学习基本动作",
      "estimated_cost": 300,
      "duration_hours": 2
    }
  ]
}
```

**文化数据库结构** (需建立):
```
文化库/
├── 城市文化档案/
│   └── 安庆/
│       ├── 非遗项目.json         (黄梅戏、手工艺等)
│       ├── 历史文化.json         (古迹、故事)
│       ├── 民俗传统.json         (节庆、风俗)
│       └── 推荐活动.json         (表演、工坊等)
├── 文化匹配规则.json            (用户偏好 → 推荐主题)
└── 文化说明库.json              (景点故事和背景)
```

---

#### **3. 路由优化Agent** ✅

**现状**：已实现  
**位置**：`Multi-agent/Route/route_planning_agent.py`

**核心职责**：

| 功能 | 说明 |
|-----|------|
| **POI聚类** | 按地理位置分组相近景点，避免来回奔波 |
| **路线优化** | 使用TSP算法、贪心算法、遗传算法求解最优访问顺序 |
| **停留时间** | 为每个景点估算合理的停留时间 |
| **多方案生成** | 提供"快速路线"、"文化路线"、"美食路线"等选项 |
| **约束验证** | 检查距离、时间、交通方式的可行性 |

**输入**：
- 文化景点列表（来自文化Agent）
- 用户时间偏好和交通工具

**输出**：
```json
{
  "optimized_routes": [
    {
      "route_id": "route_cultural",
      "name": "文化沉浸路线",
      "days": 3,
      "itinerary": [
        {
          "day": 1,
          "pois": [
            {
              "poi_name": "黄梅戏博物馆",
              "arrival_time": "09:00",
              "departure_time": "11:00",
              "duration_minutes": 120,
              "transport_to_next": "驾车",
              "distance_km": 5
            }
          ]
        }
      ],
      "total_distance_km": 85,
      "total_duration_hours": 16
    }
  ]
}
```

---

#### **4. 费用规划Agent** 🆕

**职责**：确保旅行**物有所值，在预算内获得最佳体验**

**输入**：
- 用户预算和人数
- 景点和活动列表
- 路线方案（来自路由Agent）

**核心功能**：

| 功能 | 说明 | 例子 |
|-----|------|------|
| **成本估算** | 计算各项成本 | 门票×人数、餐饮×天数等 |
| **预算分配** | 优先级分配各类支出 | 文化体验优先，住宿次之 |
| **性价比优化** | 找免费/优惠景点、推荐平价餐厅 | 推荐"免费开放"的景点 |
| **成本预警** | 标记超预算项 | "当前方案超预算12%，建议..." |
| **成本降级方案** | 提供备选方案 | "用民宿替代酒店，节省50%" |

**输出**：
```json
{
  "total_budget": 5000,
  "people": 2,
  "budget_per_person": 2500,
  
  "budget_allocation": {
    "attractions": {
      "allocated": 800,
      "recommended_percentage": 16,
      "description": "景点门票和特色体验"
    },
    "dining": {
      "allocated": 1500,
      "recommended_percentage": 30,
      "description": "含特色美食"
    },
    "accommodation": {
      "allocated": 1200,
      "recommended_percentage": 24,
      "description": "经济型酒店/民宿"
    },
    "transportation": {
      "allocated": 600,
      "recommended_percentage": 12,
      "description": "高铁、出租车等"
    },
    "reserve": {
      "allocated": 900,
      "recommended_percentage": 18,
      "description": "应急和灵活支出"
    }
  },
  
  "detailed_costs": [
    {
      "category": "景点门票",
      "items": [
        {
          "name": "黄梅戏博物馆",
          "unitPrice": 60,
          "quantity": 2,
          "subtotal": 120
        }
      ],
      "subtotal": 520
    }
  ],
  
  "budget_status": "正常（超预算2%）",
  "recommendations": [
    "景点门票建议购买套票，可节省15%",
    "推荐在地方餐厅用餐，人均50-80元"
  ]
}
```

**价格数据库** (需建立):
```
价格库/
├── 门票价格/
│   └── 安庆/
│       ├── 黄梅戏博物馆.json
│       └── ...
├── 餐饮成本/
│   └── 安庆/
│       ├── 高档餐厅_人均150.json
│       ├── 中档餐厅_人均50.json
│       └── 街边小吃_人均20.json
├── 住宿参考价/
│   └── 安庆/
│       ├── 豪华酒店_300+.json
│       ├── 中档酒店_100-200.json
│       └── 民宿_80-150.json
└── 交通成本/
    └── 参考里程价格表.json
```

---

#### **5. 运营优化Agent** 🆕

**职责**：优化**体验流畅度**，避免倔强的日程和意外情况

**输入**：
- 路线方案（来自路由Agent）
- 费用分配（来自费用Agent）
- 旅行人群信息（人数、年龄、体质等）

**核心功能**：

| 功能 | 说明 | 例子 |
|-----|------|------|
| **时间优化** | 避免排队、最大化体验 | "景A上午游客多，建议下午去" |
| **休息规划** | 根据游览强度安排休息 | "上午2小时强度游览后，午餐+休息1.5小时" |
| **体验流畅度** | 减少往返、合理分组 | "两个景点距离近，可组合为一个行程块" |
| **应急预案** | 准备备选方案 | 如遇下雨，推荐室内景点和活动 |
| **节奏调整** | 根据人群特点调整 | 老年人：缩短行走距离，增加休息 |

**输出**：
```json
{
  "optimized_itinerary": [
    {
      "day": 1,
      "theme": "文化启蒙日",
      "schedule": [
        {
          "time": "08:00-09:00",
          "activity": "早餐 + 准备",
          "location": "酒店",
          "notes": "推荐酒店周边的早点摊"
        },
        {
          "time": "09:00-11:30",
          "activity": "黄梅戏博物馆参观",
          "location": "黄梅戏博物馆",
          "tips": "早上9点开门，游客较少，推荐此时到达",
          "duration_minutes": 120,
          "intensity": "中等"
        },
        {
          "time": "11:30-12:30",
          "activity": "文化咖啡融合餐",
          "location": "博物馆附近",
          "tips": "推荐戏曲主题餐厅，氛围独特",
          "cost_estimate": 100,
          "duration_minutes": 60
        }
      ]
    }
  ],
  
  "rest_recommendations": [
    {
      "day": 1,
      "time": "14:30-15:30",
      "reason": "上午行走2.5小时，建议午休1小时"
    }
  ],
  
  "contingency_plans": [
    {
      "scenario": "下雨天第二天行程受影响",
      "alternative_activities": [
        "室内：黄梅戏博物馆特别讲座",
        "室内：民俗工艺工坊体验"
      ]
    },
    {
      "scenario": "某景点排队超过30分钟",
      "action": "改为参观附近的免费文化展馆"
    }
  ],
  
  "flexibility_buffer": {
    "reason": "为突发事件预留灵活时间",
    "time": "每天下午16:00-17:30 自由时间"
  }
}
```

---

## 🔄 Agent工作流程

### 执行顺序

```
┌─────────────────────────────────────────┐
│ Step 0: 主控Agent - 意图识别             │
│ 输入：用户原始问询                       │
│ 输出：结构化意图 + 执行计划              │
└────────────────┬────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
    ▼                         ▼
┌──────────────────────┐  ┌──────────────────┐
│ Step 1a:             │  │ Step 1b(parallel)│
│ 数据采集Agent        │  │ (可选其他预处理) │
│ 输出：原始POI数据    │  │                  │
└────────────┬─────────┘  └──────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 2: 文化体验Agent (串联)             │
│ 输入：用户偏好 + POI列表                 │
│ 输出：筛选 + 排序的文化景点              │
└────────────┬─────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 3: 路由优化Agent (串联)             │
│ 输入：文化景点 + 时间约束                │
│ 输出：多个优化路线方案                   │
└────────────┬─────────────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
┌──────────────┐  ┌──────────────────┐
│ Step 4a:     │  │ Step 4b(parallel)│
│ 费用规划Agent│  │ (可选)           │
│ 输出：成本表 │  │                  │
└──────────────┘  └──────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 5: 运营优化Agent (串联)             │
│ 输入：路线 + 费用 + 用户特征             │
│ 输出：最终行程表 + 应急预案              │
└────────────┬─────────────────────────────┘
             │
             ▼
┌──────────────────────────────────────────┐
│ Step 6: 主控Agent - 结果融合             │
│ 输入：所有Agent的输出                    │
│ 输出：最终规划方案（JSON）               │
└──────────────────────────────────────────┘
```

### 数据流动示意

```
用户输入
  ▼
【主控】提取意图
  ▼
【数据采集】→ POI_LIST, WEATHER, ROUTES
  ▼ (共享上下文)
【文化体验】→ CULTURAL_POIS, ACTIVITIES
  ▼ (共享上下文)
【路由优化】→ OPTIMIZED_ROUTES
  ▼ (共享上下文)
【费用规划】→ BUDGET_ALLOCATION, COST_DETAILS
  ▼ (共享上下文)
【运营优化】→ FINAL_ITINERARY, CONTINGENCY_PLANS
  ▼
【主控】融合结果
  ▼
最终规划 (JSON) → Web UI
```

---

## 💾 共享数据结构 (PlanningContext)

所有Agent共享一个统一的**上下文对象**，避免数据重复传输：

```python
class PlanningContext:
    """多Agent共享的规划上下文"""
    
    # 1. 用户意图 (Step 0 生成)
    user_intent: {
        "destination": "安庆",
        "duration": 3,
        "budget": 5000,
        "people": 2,
        "preferences": ["黄梅戏", "乡村文化", "美食"]
    }
    
    # 2. 原始数据 (Step 1 生成)
    raw_data: {
        "pois": [...],           # 所有POI
        "weather": {...},        # 天气
        "routes": [...]          # 路线距离时间
    }
    
    # 3. 文化处理 (Step 2 生成)
    cultural_data: {
        "cultural_theme": "黄梅戏+乡村体验",
        "cultural_pois": [...],  # 筛选后的景点
        "activities": [...]      # 推荐活动
    }
    
    # 4. 路线优化 (Step 3 生成)
    route_data: {
        "optimized_routes": [...],
        "route_details": {...}
    }
    
    # 5. 费用规划 (Step 4 生成)
    budget_data: {
        "budget_allocation": {...},
        "cost_breakdown": [...]
    }
    
    # 6. 运营优化 (Step 5 生成)
    operational_data: {
        "final_itinerary": {...},
        "contingency_plans": [...]
    }
```

---

## ⚖️ 冲突解决规则

当多个Agent给出矛盾建议时，主控Agent按以下优先级决策：

| 优先级 | 冲突类型 | 决策规则 |
|------|--------|--------|
| **1** | 用户硬性需求 | 用户意图 >  所有其他建议<br/>例：用户说"必须体验黄梅戏"，就必须包含 |
| **2** | 文化体验 vs 其他 | 文化优先<br/>理由：文化是核心差异点 |
| **3** | 费用 vs 时间 | 在预算内找最好体验<br/>可调整行程避免超预算 |
| **4** | 体验 vs 效率 | 平衡原则<br/>不能太仓促（每天>8小时连续行走），也不能太悠闲 |
| **5** | 景点数量 vs 体验深度 | 优先深度<br/>宁可少去几个景点，充分体验文化底蕴 |

**冲突解决示例**：

场景：路由Agent提议6个景点，但预算Agent警告会超支20%

解决过程：
1. 主控询问：是否有低成本文化代替方案？
2. 文化Agent：提议用免费讲座替代某个景点
3. 路由Agent：调整路线，去掉最偏远的景点
4. 费用Agent：确认新方案在预算内
5. 主控：采纳修改后的方案

---

## 📊 实现优先级

**Phase 1: MVP (第一阶段)**
- ✅ 主控Agent (已有)
- ✅ 路由优化Agent (已有)
- 🔧 数据采集Agent (完善)
- 🔧 文化体验Agent (新增)**【关键】**

**Phase 2: 完整系统 (第二阶段)**
- 🔧 费用规划Agent (新增)
- 🔧 运营优化Agent (新增)
- 🔧 冲突解决机制 (完善)
- 🔧 Web前端集成

**Phase 3: 优化和扩展**
- 用户偏好学习
- 多语言支持
- 图像识别（景点照片）
- 社交分享和评价

---

## 🛠️ 技术实现（LangChain框架）

### 总体架构

采用 **LangChain 多Agent框架**，实现Agent间的智能协作和迭代调整：

```
┌──────────────────────────────────────────────────────────┐
│                    前端 (模块化展示)                       │
│  [ 规划模块 | 文化模块 | 预算模块 | 导航模块 | 知识库 ]    │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│              LangChain Agent Orchestrator                 │
│                                                           │
│  • 意图解析 + 动态路由                                    │
│  • Agent任务分配和监督                                    │
│  • 迭代反馈和冲突解决                                     │
│  • 结果质量评估                                           │
└──────┬───────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent 工作池 (LangChain)                 │
│  [工具调用] ← → [Agent状态管理] ← → [内存管理]              │
│                                                              │
│  Agent 1: 数据采集Agent         ✓ 获取原始数据              │
│  Agent 2: 文化体验Agent         ✓ 文化筛选和故事生成        │
│  Agent 3: 路由优化Agent         ✓ 路线规划                  │
│  Agent 4: 费用规划Agent         ✓ 成本估算和优化            │
│  Agent 5: 运营优化Agent         ✓ 时间调度和应急方案        │
│  Agent 6: 质量评估Agent(新增)   ✓ 检查方案是否符合要求      │
└─────────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│               外部API和数据源                             │
│  • 高德地图API     • DeepSeek LLM                          │
│  • 知识库数据库    • 多模态数据处理                        │
└──────────────────────────────────────────────────────────┘
```

### 代码结构 (新)

```
Multi-agent/
├── __init__.py
│
├── 📁 core/                           # 核心框架
│   ├── base_agent.py                  # LangChain Agent基类
│   ├── agent_memory.py                # Agent内存管理
│   ├── planning_context.py            # 规划上下文
│   ├── agent_state.py                 # Agent状态机
│   └── tools_registry.py              # 工具注册中心
│
├── 📁 agents/                         # 具体Agent实现
│   ├── data_collection_agent.py       # 数据采集
│   ├── culture_agent.py               # 文化体验
│   ├── route_agent.py                 # 路由优化
│   ├── budget_agent.py                # 费用规划
│   ├── operation_agent.py             # 运营优化
│   └── quality_eval_agent.py          # 质量评估(新增)
│
├── 📁 orchestrator/                   # 主控协调器 (移过来)
│   ├── orchestrator.py                # 主协调逻辑
│   ├── agent_router.py                # Agent路由
│   ├── feedback_loop.py               # 反馈和调整 (新增)
│   ├── conflict_resolver.py           # 冲突解决
│   └── result_aggregator.py           # 结果聚合
│
├── 📁 knowledge_base/                 # 增量知识库 (新增)
│   ├── kb_manager.py                  # 知识库管理器
│   ├── kb_storage.py                  # 持久化存储
│   ├── kb_retriever.py                # 检索和学习
│   └── multimodal_handler.py          # 多模态处理
│
├── 📁 api_client/                     # API客户端
│   ├── amap_client.py                 # 高德地图
│   ├── deepseek_client.py             # DeepSeek LLM
│   ├── multimodal_client.py           # 多模态API(图像识别等)
│   └── cache_manager.py               # 缓存管理
│
├── 📁 tools/                          # LangChain工具集
│   ├── search_tools.py                # 搜索工具
│   ├── calculation_tools.py           # 计算工具
│   ├── route_tools.py                 # 路线工具
│   └── validation_tools.py            # 验证工具
│
├── requirements.txt                   # 依赖 (langchain, langsmith等)
├── config.py                          # 配置管理
├── main.py                            # 统一入口
├── test_agents.py                     # 测试套件
└── README.md                          # 实现文档
```

### 核心概念：Agent间协作机制

#### 1. **迭代反馈循环** (Feedback Loop)

```
        ┌─────────────────────────────┐
        │   Agent A 输出初步方案       │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │   Agent B 审查和优化        │
        │   • 检查数据完整性          │
        │   • 提出改进建议            │
        │   • 返回反馈意见            │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │   Agent A 接收反馈          │
        │   • 调整参数                │
        │   • 重新执行                │
        │   • 返回优化结果            │
        └──────────────┬──────────────┘
                       │
        ┌──────────────▼──────────────┐
        │   质量评估 Agent            │
        │   符合要求？ ──是→ 完成      │
        │             └否→ 继续反馈
        └─────────────────────────────┘
```

#### 2. **Agent通信协议**

```python
# 每个Agent间通过标准化的消息格式通信
message = {
    "sender_agent": "culture_agent",
    "receiver_agent": "route_agent",
    "message_type": "data_request|feedback|result",
    "content": {
        "request": "请根据文化景点优化路线",
        "cultural_pois": [...],
        "constraints": {...}
    },
    "timestamp": "2026-02-24T10:30:00",
    "iteration": 1,
    "confidence_score": 0.85
}
```

#### 3. **Agent状态机**

```
        ┌─────────────┐
        │   IDLE      │ ◄─────────┐
        └──────┬──────┘           │
               │                  │
               ▼                  │
        ┌─────────────┐           │
        │  EXECUTING  │           │
        └──────┬──────┘           │
               │                  │
        ┌──────┴──────┐           │
        │             │           │
        ▼             ▼           │
    ┌────────┐  ┌──────────┐     │
    │SUCCESS │  │ FEEDBACK │─────┤ (修改参数并重试)
    └────────┘  └──────────┘     │
        │             │           │
        └─────────────┴───────────┘
              ▼
        ┌─────────────┐
        │  COMPLETED  │
        └─────────────┘
```

### LangChain 代码框架示例

#### **基础Agent类**

```python
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from abc import ABC, abstractmethod
from typing import Dict, Any, List
import json

class TravelPlanningAgent(ABC):
    """旅游规划基础Agent"""
    
    def __init__(self, name: str, llm, tools: List[BaseTool]):
        self.name = name
        self.llm = llm
        self.tools = tools
        self.memory = []  # Agent内存
        self.state = "IDLE"
        self.iteration = 0
    
    def execute(self, context: PlanningContext) -> Dict[str, Any]:
        """执行Agent业务逻辑"""
        self.state = "EXECUTING"
        self.iteration += 1
        
        try:
            # 使用LangChain的ReAct框架
            result = self._run_react_agent(context)
            self.state = "SUCCESS"
            return {
                "status": "success",
                "agent_name": self.name,
                "iteration": self.iteration,
                "result": result
            }
        except Exception as e:
            self.state = "FEEDBACK"
            return {
                "status": "error",
                "agent_name": self.name,
                "error": str(e),
                "feedback": self._generate_feedback()
            }
    
    def _run_react_agent(self, context):
        """使用ReAct框架运行Agent"""
        prompt = self._construct_prompt(context)
        agent = create_react_agent(self.llm, self.tools, prompt)
        executor = AgentExecutor.from_agent_and_tools(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=5
        )
        return executor.invoke({"input": prompt})
    
    def receive_feedback(self, feedback: Dict[str, Any]):
        """接收其他Agent的反馈"""
        self.memory.append({
            "type": "feedback",
            "content": feedback,
            "iteration": self.iteration
        })
    
    @abstractmethod
    def _construct_prompt(self, context):
        """构造Agent的提示词"""
        pass
    
    @abstractmethod
    def _generate_feedback(self):
        """生成反馈信息"""
        pass
```

#### **Orchestrator 协调器**

```python
from langchain.schema import AIMessage, HumanMessage
from langgraph.graph import StateGraph, END
import asyncio

class TravelPlanningOrchestrator:
    """多Agent协调器 - 基于LangChain"""
    
    def __init__(self, agents_list: List[TravelPlanningAgent]):
        self.agents = {agent.name: agent for agent in agents_list}
        self.context = PlanningContext()
        self.execution_history = []
        self.max_iterations = 5
    
    async def run_planning(self, user_input: str) -> Dict[str, Any]:
        """执行完整的规划流程"""
        
        # Step 1: 解析意图
        self.context.user_intent = self._parse_intent(user_input)
        
        # Step 2: 迭代执行Agent
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            print(f"\n=== Iteration {iteration} ===")
            
            # 按顺序执行Agent
            agent_results = {}
            for agent_name in self._get_execution_order():
                agent = self.agents[agent_name]
                result = agent.execute(self.context)
                agent_results[agent_name] = result
                
                # 更新上下文
                self._update_context(agent_name, result)
            
            # Step 3: 质量评估
            quality = self._evaluate_quality(agent_results)
            if quality["is_acceptable"]:
                print(f"✓ 质量评估通过 (Score: {quality['score']:.2f})")
                break
            else:
                print(f"✗ 质量评估未通过 (Score: {quality['score']:.2f})")
                print(f"  建议改进: {quality['suggestions']}")
                
                # 反馈给相关Agent
                self._send_feedback(agent_results, quality)
        
        # 最终融合结果
        final_result = self._aggregate_results(agent_results)
        return final_result
    
    def _get_execution_order(self) -> List[str]:
        """获取Agent执行顺序"""
        return [
            "data_collection_agent",
            "culture_agent",
            "route_agent",
            "budget_agent",
            "operation_agent",
            "quality_eval_agent"
        ]
    
    def _evaluate_quality(self, results: Dict) -> Dict[str, Any]:
        """评估规划质量"""
        quality_agent = self.agents.get("quality_eval_agent")
        if not quality_agent:
            return {"is_acceptable": True, "score": 1.0}
        
        # 使用质量评估Agent检查
        evaluation = quality_agent.evaluate(results, self.context)
        return evaluation
    
    def _send_feedback(self, results: Dict, quality: Dict):
        """向需要改进的Agent发送反馈"""
        for agent_name, feedback_msg in quality.get("feedback_per_agent", {}).items():
            if agent_name in self.agents:
                self.agents[agent_name].receive_feedback(feedback_msg)
    
    def _aggregate_results(self, results: Dict) -> Dict[str, Any]:
        """聚合所有Agent的结果"""
        return {
            "itinerary": results.get("operation_agent", {}).get("result", {}),
            "cultural_insights": results.get("culture_agent", {}).get("result", {}),
            "routes": results.get("route_agent", {}).get("result", {}),
            "budget_plan": results.get("budget_agent", {}).get("result", {}),
            "execution_history": self.execution_history
        }
```

### 前端模块化展示设计

```
┌─────────────────────────────────────────────────────────┐
│              多Agent规划系统 前端UI                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 🔍 规划进度 | 当前执行: 费用规划Agent            │  │
│  │ Iteration: 2/5 | 质量评分: 0.82/1.0              │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌─────────────┬─────────────┬─────────────┬────────┐  │
│  │ 📋 规划模块 │ 🎭 文化模块 │ 💰 预算模块 │ 🗺️ 导航 │  │
│  └─────────────┴─────────────┴─────────────┴────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │ 📋 完整行程方案                                 │   │
│  │                                                 │   │
│  │ 🗓️ Day 1 - 文化启蒙日                          │   │
│  │  ├─ 09:00-11:00 黄梅戏博物馆参观              │   │
│  │  │  └─ 💡 提示: 周二限量讲座，提前预约(可点)   │   │
│  │  ├─ 11:00-13:00 特色午餐                      │   │
│  │  └─ 14:00-17:00 民俗手工基地体验              │   │
│  │                                                 │   │
│  │ [📝 复制行程] [🗺️ 查看地图] [👥 分享] [💾 保存]  │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │ 🎭 文化体验模块                                 │   │
│  │                                                 │   │
│  │ 📖 推荐主题: 黄梅戏非遗文化 + 江南乡村体验     │   │
│  │                                                 │   │
│  │ 🖼️ [黄梅戏博物馆图片]  [民俗手工坊图片]      │   │
│  │                                                 │   │
│  │ 📚 黄梅戏背景:                                  │   │
│  │   "黄梅戏起源于安庆地区...被誉为中国第五大戏曲" │   │
│  │                                                 │   │
│  │ 🎪 推荐特色活动:                               │   │
│  │   • 19:00 黄梅戏表演 (¥200/8折优惠)           │   │
│  │   • 沉浸式戏曲体验 (¥300)                      │   │
│  │                                                 │   │
│  │ [🔗 更多文化资源]                               │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │ 💰 预算模块                                     │   │
│  │                                                 │   │
│  │ 总预算: ¥5000 | 人均: ¥2500 | 状态: ✓ 在预算内  │   │
│  │                                                 │   │
│  │ 预算分配:                                       │   │
│  │ ├─ 景点门票 ¥800 (16%) [████░░░░░░]           │   │
│  │ ├─ 餐饮费用 ¥1500 (30%) [████████░]           │   │
│  │ ├─ 住宿费用 ¥1200 (24%) [██████░░░]           │   │
│  │ ├─ 交通费用 ¥600 (12%) [███░░░░░░]            │   │
│  │ └─ 应急预留 ¥900 (18%) [█████░░░░]            │   │
│  │                                                 │   │
│  │ 💡 优化建议:                                    │   │
│  │   ✓ 景点套票可节省15%                           │   │
│  │   ✓ 推荐地方餐厅(人均50-80元)                  │   │
│  │                                                 │   │
│  │ [📊 详细成本表] [💾 导出预算]                   │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │ 🗺️ 导航模块                                     │   │
│  │                                                 │   │
│  │ [Leaflet 交互式地图]                            │   │
│  │ - 景点位置标记                                  │   │
│  │ - 路线规划 (驾车/公交/步行)                      │   │
│  │ - 距离和耗时信息                                │   │
│  │ - 点击景点查看详情                              │   │
│  │                                                 │   │
│  │ [📍 导出GPX] [🧭 方向导航] [📱 分享位置]        │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │ 📚 知识库模块                                   │   │
│  │                                                 │   │
│  │ 最近学到的知识:                                 │   │
│  │ • 黄梅戏表演时间表 (2026-03更新)               │   │
│  │ • 安庆特色手工艺工坊联系方式                    │   │
│  │ • 乡村民宿推荐名单                              │   │
│  │                                                 │   │
│  │ [🔍 搜索知识库] [➕ 新增知识] [📊 知识统计]     │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────────────────────────────────┐   │
│  │ ⚙️ Agent执行详情                               │   │
│  │                                                 │   │
│  │ █ 数据采集Agent       ✓ (0.8s)                 │   │
│  │ █ 文化体验Agent       ✓ (1.2s)    # Iteration │   │
│  │ █ 路由优化Agent       ✓ (2.1s)             2  │   │
│  │ █ 费用规划Agent       ► (0.5s) 执行中...       │   │
│  │ ░ 运营优化Agent       ⏳ 等待中                 │   │
│  │ ░ 质量评估Agent       ⏳ 等待中                 │   │
│  │                                                 │   │
│  │ [📋 查看完整日志] [🔄 重新规划]                 │   │
│  └────────────────────────────────────────────────┘   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 增量知识库系统

```python
# 📁 knowledge_base/kb_manager.py

from datetime import datetime
import json
from pathlib import Path

class KnowledgeBaseManager:
    """增量知识库管理器"""
    
    def __init__(self, kb_path: str = "data/knowledge_base"):
        self.kb_path = Path(kb_path)
        self.kb_path.mkdir(parents=True, exist_ok=True)
    
    def learn_from_result(self, agent_name: str, result: Dict, 
                         multimodal_data: Dict = None):
        """从Agent执行结果中学习"""
        knowledge = {
            "timestamp": datetime.now().isoformat(),
            "source": agent_name,
            "type": "execution_result",
            "content": result,
            "multimodal": multimodal_data or {},
            "tags": self._extract_tags(result),
            "confidence": 0.85
        }
        
        # 存储到知识库
        self._store_knowledge(knowledge)
        
        # 建立关联 (用于后续检索)
        self._index_knowledge(knowledge)
    
    def learn_from_feedback(self, feedback: Dict):
        """从反馈中学习"""
        knowledge = {
            "timestamp": datetime.now().isoformat(),
            "type": "feedback",
            "content": feedback,
            "tags": ["feedback", "correction"],
            "confidence": 0.9
        }
        self._store_knowledge(knowledge)
    
    def learn_from_user_correction(self, original: Dict, correction: Dict):
        """从用户纠正中学习"""
        knowledge = {
            "timestamp": datetime.now().isoformat(),
            "type": "user_feedback",
            "original": original,
            "correction": correction,
            "tags": ["user_correction"],
            "confidence": 1.0  # 用户反馈最可信
        }
        self._store_knowledge(knowledge)
    
    def retrieve_similar(self, query: Dict, limit: int = 5) -> List[Dict]:
        """检索相似的历史知识"""
        # 使用向量相似度或其他检索策略
        pass
    
    def _store_knowledge(self, knowledge: Dict):
        """持久化存储知识"""
        timestamp = knowledge["timestamp"].replace(":", "-")
        file_path = self.kb_path / f"{timestamp}_{knowledge['type']}.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(knowledge, f, ensure_ascii=False, indent=2)
    
    def _index_knowledge(self, knowledge: Dict):
        """建立索引以加快检索"""
        # 可以使用 Elasticsearch、Milvus 等向量数据库
        pass
    
    def _extract_tags(self, result: Dict) -> List[str]:
        """从结果中提取标签"""
        tags = []
        if "destination" in result:
            tags.append(f"dest_{result['destination']}")
        if "themes" in result:
            tags.extend(result["themes"])
        return tags
```

### 使用示例

```python
from multi_agent.main import run_travel_planning

# 初始化系统
async def main():
    user_input = "安庆3天，体验黄梅戏文化，预算5000元"
    
    result = await run_travel_planning(
        user_input=user_input,
        enable_multimodal=True,  # 启用多模态处理
        save_to_kb=True           # 结果保存到知识库
    )
    
    # 结果为模块化的字典
    print("=== 规划结果 ===")
    print(f"✓ 行程: {result['itinerary']}")
    print(f"✓ 文化: {result['cultural_insights']}")
    print(f"✓ 预算: {result['budget_plan']}")
    print(f"✓ 导航: {result['routes']}")
    
    # 返回给前端
    return result
```

---

## 📝 下一步行动

### 已完成的框架工作 ✅

- ✓ PlanningContext - 统一的共享数据结构
- ✓ Agent状态机 - 完整的生命周期管理
- ✓ Agent内存系统 - 短期+长期记忆
- ✓ TravelPlanningAgent基类 - 标准化Agent框架
- ✓ KnowledgeBaseManager - 增量知识库系统
- ✓ UIModuleFactory - 前端模块化展示
- ✓ 完整的设计文档和实现指南

### 待完成的任务 (按优先级)

**Phase 1: 核心Agent实现** (优先级: 🔴 最高)
- [ ] **DataCollectionAgent** - 数据采集
  - 集成高德地图API
  - POI搜索、天气、路线查询
  - 缓存管理
- [ ] **CultureAgent** - 文化体验 【关键】
  - 文化主题识别
  - 文化景点筛选和排序
  - 故事和背景生成
  - 多模态资源整合
- [ ] **QualityEvalAgent** - 质量评估
  - 规划方案校验
  - 冲突检测
  - 可行性分析

**Phase 2: Agent协调层** (优先级: 🟠 高)
- [ ] **TravelOrchestrator** - 主协调器
  - 意图识别
  - Agent路由和调度
  - 反馈循环
  - 冲突解决
- [ ] **其他Agent改进**
  - RouteOptimizationAgent (改进版)
  - BudgetAgent 费用规划
  - OperationAgent 运营优化

**Phase 3: 系统集成** (优先级: 🟡 中)
- [ ] API客户端 (高德、DeepSeek)
- [ ] LangChain工具集成
- [ ] 前端API接口
- [ ] 测试和优化

### 数据库需求

| 数据库 | 优先级 | 数据量 | 备注 |
|------|------|--------|------|
| 文化档案库 | 高 | 1000条+ | 非遗、历史、活动等 |
| 价格参考库 | 中 | 500条+ | 门票、餐饮、住宿 |
| 景点故事库 | 中 | 200条+ | 文化背景说明 |
| 活动库 | 高 | 100条+ | 推荐特色活动 |

### 前端模块展示实现

**前端接收的JSON结构** (模块化设计):

```json
{
  "status": "success",
  "session_id": "abc12345",
  "quality_score": 0.92,
  "iteration": 2,
  "modules": {
    "itinerary": {
      "days": 3,
      "schedule": [
        {
          "day": 1,
          "activities": [
            {
              "time": "09:00-11:00",
              "activity": "黄梅戏博物馆参观",
              "duration_minutes": 120,
              "tips": "早上人少，建议此时到达"
            }
          ]
        }
      ]
    },
    "culture": {
      "theme": "黄梅戏非遗文化 + 江南乡村体验",
      "sites": [
        {
          "name": "黄梅戏博物馆",
          "priority": 1,
          "story": "黄梅戏起源于...",
          "images": ["url1", "url2"]
        }
      ]
    },
    "budget": {
      "total_budget": 5000,
      "status": "正常 (99%)",
      "breakdown": {...}
    },
    "navigation": {
      "map_center": {"lat": 30.6, "lng": 117.05},
      "pois": [...],
      "routes": [...]
    },
    "knowledge": {
      "recent_learnings": [...],
      "categories": {"cultural": 45, "pricing": 23}
    },
    "execution": {
      "iteration": 2,
      "agents_status": [
        {"name": "data_agent", "status": "success"},
        {"name": "culture_agent", "status": "success"},
        ...
      ]
    },
    "contingency": {
      "scenarios": [
        {"scenario": "下雨", "alternative": "室内景点"}
      ]
    }
  }
}
```

**前端展示策略**:

1. **顶部进度条** - 显示迭代进度 (2/5)
2. **Tab切换** - 7个模块分别显示
3. **实时更新** - WebSocket推送Agent执行进度
4. **导出功能** - PDF、分享等
5. **交互式地图** - Leaflet显示POI和路线

---

## 📞 沟通方式

- **设计讨论**：在这个文档中更新设计
- **代码实现**：Pull Request制度
- **测试验收**：集成测试通过标准
- **定期会议**：周二下午2点同步进展

---

**最后更新时间**：2026年2月24日  
**维护人员**：项目团队
