"""
多Agent旅游规划系统 - 快速开始指南
"""

# ═══════════════════════════════════════════════════════════════════
#
#  🚀 Traveling-v2 多Agent系统
#
#  构建完整的LangChain多Agent工作流
#  支持Agent间协作、反馈调整、增量学习
#
# ═══════════════════════════════════════════════════════════════════

"""
## 🎯 系统特点

✅ **完整的Agent框架**
   • 标准化的Agent基类和生命周期管理
   • Agent状态机 (7个状态)
   • 短期+长期内存系统
   • 反馈接收和处理机制

✅ **智能协作机制**
   • 共享规划上下文 (PlanningContext)
   • Agent间通信协议
   • 反馈循环和迭代调整
   • 质量评估和冲突解决

✅ **知识积累系统**
   • 自动从执行结果中学习
   • 多模态数据支持 (文字+图片/视频)
   • 分类索引和语义检索
   • 用户纠正学习

✅ **前端模块化展示**
   • 7个独立模块 (行程、文化、预算、导航、知识库、执行、应急)
   • UIModuleFactory自动转换
   • JSON结构化数据
   • 模块组件化架构

✅ **多模态支持**
   • 图片资源集成
   • 视频内容处理
   • 文化背景图文展示
   • 景点图库管理

## 📁 项目结构

```
Multi-agent/
├── core/                           ✅ 已实现
│   ├── base_agent.py               - Agent基类
│   ├── planning_context.py         - 共享上下文
│   ├── agent_state.py              - 状态机
│   └── agent_memory.py             - 内存管理
│
├── knowledge_base/                 ✅ 已实现
│   └── kb_manager.py               - 知识库管理
│
├── ui_modules.py                   ✅ 已实现
│   - UIModuleFactory基类和
│   - UIResponseBuilder
│
├── agents/                         ⏳ 待实现 (优先级最高)
│   ├── data_collection_agent.py    - 数据采集
│   ├── culture_agent.py            - 文化体验【关键】
│   ├── route_agent.py              - 路由优化
│   ├── budget_agent.py             - 费用规划
│   ├── operation_agent.py          - 运营优化
│   └── quality_eval_agent.py       - 质量评估
│
├── orchestrator/                   ⏳ 待实现
│   ├── orchestrator.py             - 主协调器
│   ├── feedback_loop.py            - 反馈机制
│   └── conflict_resolver.py        - 冲突解决
│
└── IMPLEMENTATION_GUIDE.md         ✅ 实现指南
```

## 💻 快速开始

### 1. 安装依赖

```bash
cd Multi-agent
pip install -r requirements.txt
```

### 2. 创建一个简单的Agent

```python
from core.base_agent import TravelPlanningAgent
from core.planning_context import PlanningContext

class SimpleAgent(TravelPlanningAgent):
    def __init__(self):
        super().__init__(name="simple_agent")
    
    def _validate_input(self, context: PlanningContext) -> bool:
        return True
    
    def _execute_core(self, context: PlanningContext) -> dict:
        # 实现业务逻辑
        return {"status": "completed"}

# 使用
agent = SimpleAgent()
context = PlanningContext()
output = agent.execute(context)
print(output)
```

### 3. 使用知识库

```python
from knowledge_base import KnowledgeBaseManager

kb = KnowledgeBaseManager()

# 学习新知识
kb.learn_from_agent_output("agent_name", agent_result)

# 查询知识
results = kb.retrieve_knowledge("黄梅戏", limit=5)

# 查看统计
stats = kb.get_kb_statistics()
print(f"知识库中有 {stats['total_knowledge']} 条知识")
```

### 4. 前端集成

```python
from ui_modules import UIResponseBuilder

# 构建前端响应
response = UIResponseBuilder.build_full_response(context, kb)

# 返回给Web前端
import json
return json.dumps(response, ensure_ascii=False)
```

## 🔧 核心 API

### PlanningContext - 共享数据结构

```python
context = PlanningContext()

# 用户意图
context.user_intent  # UserIntent 对象

# 原始数据
context.pois         # POI列表
context.weather      # 天气数据
context.routes       # 路线数据

# 文化处理
context.cultural_pois
context.cultural_activities
context.cultural_background

# 路由优化
context.optimized_routes
context.selected_route

# 费用规划
context.budget_allocation
context.cost_details

# 运营优化
context.final_itinerary
context.contingency_plans

# 管理
context.add_agent_output(output)
context.get_agent_output("agent_name")
context.to_dict()
context.to_json()
```

### Agent 生命周期

```python
# 创建Agent
agent = MyAgent()

# 执行
output = agent.execute(context)
# 输出: AgentOutput
#   - agent_name: str
#   - iteration: int
#   - status: str (success/error/feedback)
#   - result: dict
#   - confidence_score: float

# 接收反馈
agent.receive_feedback(
    feedback={"suggestions": "..."},
    from_agent="other_agent"
)

# 再次执行 (会处理反馈)
output2 = agent.execute(context)

# 查看状态
status = agent.get_status()
# 返回: 执行计数、成功率、内存信息等

# 重置
agent.reset()
```

### Agent内存系统

```python
# 短期记忆 (recent operations)
agent.memory.get_recent_memories(count=5)

# 中期反馈
agent.memory.get_unprocessed_feedback()
agent.memory.mark_feedback_processed(index)

# 长期学习
agent.memory.get_important_learnings(min_score=0.7)

# 错误追踪
agent.memory.get_error_patterns()

# 内存摘要
summary = agent.memory.get_memory_summary()
```

### 知识库 API

```python
kb = KnowledgeBaseManager()

# 学习
kb.learn_from_agent_output(agent_name, output)
kb.learn_from_user_correction(original, correction)
kb.learn_from_multimodal(agent_name, image_data)

# 检索
results = kb.retrieve_knowledge(
    query="黄梅戏",
    knowledge_type="cultural_insight",
    category="cultural",
    limit=5
)

# 统计
stats = kb.get_kb_statistics()

# 导出
kb.export_knowledge("exports/", knowledge_type="price_info")
```

### 前端响应格式

```json
{
  "status": "success",
  "session_id": "abc12345",
  "quality_score": 0.92,
  "modules": {
    "itinerary": { /* 行程规划模块 */ },
    "culture": { /* 文化体验模块 */ },
    "budget": { /* 预算规划模块 */ },
    "navigation": { /* 导航地图模块 */ },
    "knowledge": { /* 知识库模块 */ },
    "execution": { /* Agent执行详情 */ },
    "contingency": { /* 应急预案 */ }
  }
}
```

## 🎓 实现向导

### Step 1: 实现DataCollectionAgent

**目标**: 集成高德API，获取POI、天气、路线数据

**关键方法**:
- `_validate_input()` - 检查目的地是否有效
- `_execute_core()` - 调用高德API获取数据

**预期输出**:
```json
{
  "pois": [...],
  "weather": {...},
  "routes": [...]
}
```

### Step 2: 实现CultureAgent 【关键】

**目标**: 识别文化主题，筛选景点，生成故事

**关键方法**:
- `_validate_input()` - 检查是否有POI列表
- `_execute_core()` - 使用LLM分析文化资源

**预期输出**:
```json
{
  "cultural_theme": "黄梅戏...",
  "cultural_pois": [...],
  "cultural_background": {...},
  "activities": [...]
}
```

### Step 3: 实现QualityEvalAgent

**目标**: 检查规划方案是否符合要求

**关键方法**:
- `_validate_input()` - 检查其他Agent的输出
- `_execute_core()` - 评估质量, return confidence_score

**预期输出**:
```json
{
  "is_acceptable": true,
  "score": 0.92,
  "suggestions": [...]
}
```

### Step 4: 实现Orchestrator

**工作流程**:
1. 解析用户意图
2. 循环 (最多5次):
   a. 按顺序执行各Agent
   b. 更新共享上下文
   c. 质量评估
   d. 如果不符合, 发送反馈
3. 融合结果
4. 返回前端

## 🧪 测试

```python
# 单元测试Agent
def test_simple_agent():
    agent = SimpleAgent()
    context = PlanningContext()
    context.user_intent = UserIntent(destination="安庆")
    
    output = agent.execute(context)
    assert output.status == "success"
    assert output.confidence_score > 0.0

# 集成测试
def test_full_workflow():
    orchestrator = TravelOrchestrator()
    result = orchestrator.run_planning("安庆3天")
    
    assert result["status"] == "success"
    assert "itinerary" in result["modules"]
```

## 🚀 部署

### 本地开发

```bash
cd Multi-agent
python main.py
```

### 与Flask/FastAPI集成

```python
from fastapi import FastAPI
from multi_agent.main import run_travel_planning

app = FastAPI()

@app.post("/api/plan")
async def create_plan(user_input: str):
    result = await run_travel_planning(user_input)
    return result
```

## 📊 系统架构图

```
┌─────────────────────────┐
│   用户输入 (Web/API)    │
└────────────┬────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│  Orchestrator                         │
│  意图识别 → Agent调度 → 反馈循环      │
└──────────┬─────────────────────────┬─┘
           │                         │
    ┌──────┴──────┐              ┌──┴────────┐
    │             │              │           │
    ▼             ▼              ▼           ▼
┌─────────┐  ┌────────┐  ┌─────────┐  ┌──────────┐
│   数据  │  │  文化  │  │  路由   │  │  质量    │
│   Agent │  │ Agent  │  │ Agent   │  │ Agent    │
└─────────┘  └────────┘  └─────────┘  └──────────┘
    │             │            │            │
    └─────────────┴────────────┴────────────┘
             │
    ┌────────▼──────────┐
    │  PlanningContext  │
    │  (共享数据)       │
    └──────────────────┘
             │
    ┌────────▼──────────┐
    │  KnowledgeBase    │
    │  (学习和记忆)     │
    └──────────────────┘
             │
    ┌────────▼──────────┐
    │  UIModuleFactory  │
    │  (前端展示)       │
    └──────────────────┘
             │
             ▼
    ┌──────────────────┐
    │ 前端 (Web UI)    │
    │ 7个模块展示      │
    └──────────────────┘
```

## 📚 文档

- [实现指南](IMPLEMENTATION_GUIDE.md) - 详细的开发步骤
- [多Agent框架设计](../Mulit-agent.md) - 系统架构和设计
- [core/](core/) - 核心框架代码
- [知识库](knowledge_base/) - 自动学习系统

## 🤝 贡献指南

1. Fork项目
2. 创建特性分支 (`git checkout -b feature/agent-xxx`)
3. 提交 Pull Request
4. 基于反馈进行调整

## ❓ 常见问题

### Q: 如何添加自定义Agent?
A: 继承`TravelPlanningAgent`类，实现`_validate_input()`和`_execute_core()`方法

### Q: 如何集成多模态数据?
A: 使用`KnowledgeBaseManager.learn_from_multimodal()`，传入图片/视频数据

### Q: 如何调整Agent的执行顺序?
A: 在Orchestrator中修改`_get_execution_order()`方法

### Q: 知识库如何导出?
A: 使用`KnowledgeBaseManager.export_knowledge()`导出为JSON

## 📞 联系方式

如有问题或建议，请提交Issue或联系团队。

---

版本: 1.0  
最后更新: 2026-02-24  
维护者: 项目团队
"""
