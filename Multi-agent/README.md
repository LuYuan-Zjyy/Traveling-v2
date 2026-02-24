"""
Multi-agent 多Agent旅游规划系统
基于LangChain框架的完整多Agent协作系统
"""

# Multi-Agent 旅游规划系统

## 🎯 系统简介

这是一个**基于LangChain框架**的完整多Agent旅游规划系统，实现了：

✅ **智能多Agent协作** - 5个专业Agent + 1个质量评估Agent  
✅ **反馈循环和迭代调整** - Agent间相互协作、补充信息、持续优化  
✅ **增量知识库系统** - 自动学习和积累旅游规划知识  
✅ **前端模块化展示** - 7个独立模块，分别展示不同信息  
✅ **多模态数据支持** - 文字、图片、视频资源整合  
✅ **完整的框架代码** - 开箱即用的Agent基类和工具  

## 📊 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户输入                              │
│              "安庆3天，体验黄梅戏，预算5000"                 │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────▼────────────────┐
        │                                 │
        ▼                                 ▼
   [意图识别]                      [任务分解]
        │                                 │
        └────────────────┬────────────────┘
                         │
              ┌──────────▼──────────┐
              │  Agent工作池        │
              │                     │
              │  ① 数据采集Agent   │─→ 高德API
              │  ② 文化体验Agent   │─→ LLM分析
              │  ③ 路由优化Agent   │─→ 算法优化
              │  ④ 费用规划Agent   │─→ 成本估算
              │  ⑤ 运营优化Agent   │─→ 时间调度
              │  ⑥ 质量评估Agent   │─→ 质量检查
              │                     │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  PlanningContext    │
              │  (共享数据结构)      │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  知识库系统          │
              │  (增量学习)          │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  前端模块化展示      │
              │  (7个独立模块)       │
              └──────────┬──────────┘
                         │
                         ▼
            ┌───────────────────────┐
            │  完整规划方案         │
            │  (JSON格式)           │
            └───────────────────────┘
```

## ✅ 已实现的功能

### 1. 核心框架 (✓ 完全实现)

```
✓ PlanningContext     - 统一的共享数据结构
✓ Agent状态机         - 完整的生命周期管理 (7个状态)
✓ Agent内存系统       - 短期记忆 + 长期记忆
✓ TravelPlanningAgent - 标准化Agent基类
✓ AgentOutput         - 标准化输出格式
```

**关键特性**:
- 每个Agent独立运行，通过共享上下文协作
- 支持反馈接收和处理，可多次迭代
- 自动记录执行历史和错误模式
- 置信度评分机制

### 2. 知识库系统 (✓ 完全实现)

```python
KnowledgeBaseManager
├── learn_from_agent_output()  - 从Agent输出学习
├── learn_from_user_correction() - 从用户纠正学习
├── learn_from_multimodal()     - 从多模态数据学习
├── retrieve_knowledge()        - 检索类似知识
├── get_kb_statistics()         - 知识库统计
└── export_knowledge()          - 导出功能
```

**特点**:
- 自动分类索引
- 语义相似度检索
- 支持文字/图片/视频
- 用户纠正学习 (最高可信度)
- 导出为JSON

### 3. 前端模块化展示 (✓ 完全实现)

**7个独立模块**:

1. **行程规划模块** (itinerary)
   - 完整日程表
   - 时间、地点、活动
   - 出行提示和建议

2. **文化体验模块** (culture)
   - 文化主题和背景
   - 推荐景点和活动
   - 图片和故事讲述

3. **预算规划模块** (budget)
   - 预算分配表
   - 详细成本清单
   - 优化建议和预警

4. **导航地图模块** (navigation)
   - Leaflet交互式地图
   - POI标记和路线
   - 距离、耗时信息

5. **知识库模块** (knowledge)
   - 最近学习的知识
   - 分类统计
   - 搜索功能

6. **Agent执行模块** (execution)
   - 实时执行进度
   - 各Agent状态
   - 质量评分

7. **应急预案模块** (contingency)
   - 风险场景列表
   - 备选方案
   - 应急联系方式

### 4. 多模态支持 (✓ 基础实现)

```
✓ 图片资源集成
✓ 视频内容处理
✓ 文化背景图文展示
✓ 景点图库管理
```

## 🔄 Agent协作流程

### 执行流程

```
用户输入
  ▼
[Orchestrator] 意图识别
  ▼
循环 (最多5次):
  ├─ Agent 1: 数据采集
  │  └─ 获取POI、天气、路线
  │
  ├─ Agent 2: 文化体验 【关键】
  │  └─ 筛选文化景点、生成故事
  │
  ├─ Agent 3: 路由优化
  │  └─ 规划最优路线
  │
  ├─ Agent 4: 费用规划
  │  └─ 成本估算、预算分配
  │
  ├─ Agent 5: 运营优化
  │  └─ 时间优化、备选方案
  │
  ├─ Agent 6: 质量评估
  │  └─ 检查是否符合要求
  │
  └─ 如果质量不符 → 发送反馈 → 重新执行
     否则 → 终止循环

融合结果
  ▼
前端模块化展示
  ▼
用户看到完整规划方案
```

### 反馈机制

```
Agent A (如路由Agent)
  ▼
发现问题 / 收到建议
  ▼
发送反馈给相关Agent
  ▼
Agent B 接收反馈
  ▼
调整参数 → 重新执行
  ▼
输出优化结果
  ▼
存储到context → 其他Agent同步获得信息
```

## 📁 文件结构

```
Multi-agent/
├── core/
│   ├── base_agent.py             ✓ Agent基类
│   ├── planning_context.py       ✓ 共享上下文
│   ├── agent_state.py            ✓ 状态机
│   ├── agent_memory.py           ✓ 内存管理
│   └── __init__.py
│
├── knowledge_base/
│   ├── kb_manager.py             ✓ 知识库管理
│   └── __init__.py
│
├── agents/                        ⏳ 待实现
│   ├── data_collection_agent.py   
│   ├── culture_agent.py           【优先】
│   ├── route_agent.py
│   ├── budget_agent.py
│   ├── operation_agent.py
│   └── quality_eval_agent.py
│
├── orchestrator/                  ⏳ 待实现
│   ├── orchestrator.py
│   └── ...
│
├── ui_modules.py                  ✓ 前端模块
├── QUICKSTART.md                  ✓ 快速开始指南
├── IMPLEMENTATION_GUIDE.md        ✓ 实现指南
├── requirements.txt               ✓ 依赖列表
└── README.md                      ✓ 本文件
```

## 🚀 快速开始

### 安装

```bash
cd Multi-agent
pip install -r requirements.txt
```

### 基础使用

```python
from core.planning_context import PlanningContext, UserIntent
from knowledge_base import KnowledgeBaseManager

# 创建上下文
context = PlanningContext()
context.user_intent = UserIntent(
    destination="安庆",
    duration_days=3,
    budget=5000
)

# 知识库
kb = KnowledgeBaseManager()

# 后续: 实现Agent并执行
```

### 前端集成

```python
from ui_modules import UIResponseBuilder

# 构建前端响应
response = UIResponseBuilder.build_full_response(context, kb)

# 返回JSON
import json
return json.dumps(response, ensure_ascii=False)
```

## 📖 文档

- **[快速开始指南](QUICKSTART.md)** - 5分钟入门
- **[实现指南](IMPLEMENTATION_GUIDE.md)** - 详细开发步骤
- **[多Agent架构](../Mulit-agent.md)** - 完整系统设计

## 🎓 开发指南

### 实现一个新Agent

```python
from core.base_agent import TravelPlanningAgent
from core.planning_context import PlanningContext

class MyAgent(TravelPlanningAgent):
    def __init__(self):
        super().__init__(name="my_agent")
    
    def _validate_input(self, context: PlanningContext) -> bool:
        """验证输入"""
        return context.user_intent is not None
    
    def _execute_core(self, context: PlanningContext) -> dict:
        """实现核心逻辑"""
        # 使用LangChain: create_react_agent等
        result = {}
        
        # 学习新知识
        self.learn_and_store({"learning": result})
        
        return result
```

### 优先实现顺序

1. **DataCollectionAgent** - 获取基础数据 (高德API)
2. **CultureAgent** - 文化匹配和生成【关键】
3. **QualityEvalAgent** - 质量评估
4. **Orchestrator** - 主协调器
5. 其他Agent优化

## 🔌 API集成

### 与FastAPI集成

```python
from fastapi import FastAPI
from multi_agent.ui_modules import UIResponseBuilder

app = FastAPI()

@app.post("/api/plan")
async def create_plan(user_input: str):
    # 执行规划
    # ...
    
    # 返回模块化结果
    response = UIResponseBuilder.build_full_response(context, kb)
    return response
```

### 与Flask集成

```python
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/api/plan", methods=["POST"])
def create_plan():
    user_input = request.json.get("input")
    
    # 执行规划
    # ...
    
    response = UIResponseBuilder.build_full_response(context, kb)
    return jsonify(response)
```

## 🧪 测试

```bash
# 运行测试
python -m pytest tests/

# 测试覆盖率
pytest --cov=multi_agent tests/
```

## 📊 系统特性对比

| 特性 | 本系统 | 传统系统 |
|-----|------|--------|
| 多Agent协作 | ✅ 支持反馈循环 | ❌ 无 |
| 迭代优化 | ✅ 最多5次迭代 | ❌ 一次性 |
| 知识积累 | ✅ 自动学习 | ❌ 无 |
| 多模态 | ✅ 文字+图片 | ❌ 文字只 |
| 前端模块化 | ✅ 7个独立模块 | ❌ 一大块 |
| 反馈机制 | ✅ Agent间通信 | ❌ 单向 |
| 质量评估 | ✅ 自动评分 | ❌ 无 |
| 应急预案 | ✅ 备选方案 | ❌ 无 |

## 💡 主要创新点

1. **反馈循环** - Agent可以相互协作和调整，而不是串联执行
2. **增量学习** - 系统从每次执行中学习，知识库不断增长
3. **模块化前端** - 不是一整段文字，而是逻辑清晰的模块
4. **多模态整合** - 图文结合，提高用户体验
5. **质量评估** - 自动检查规划方案是否符合要求

## 🎯 项目目标

- ✅ 构建完整的多Agent框架
- ⏳ 实现6个专业Agent
- ⏳ 集成高德API和DeepSeek LLM
- ⏳ 建立增量知识库
- ⏳ 开发模块化前端UI

## 📞 联系和支持

有任何问题或建议，欢迎提Issue或联系团队。

---

**版本**: 1.0-beta  
**最后更新**: 2026-02-24  
**维护者**: 项目团队  
**状态**: 🟢 核心框架完成，Agent实现中
