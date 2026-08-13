# 重构计划：按原始设计实施

## 📋 当前问题总结

### 1. 未集成核心依赖
- ❌ 没有使用vendor/luopan
- ❌ 没有使用vendor/ai-berkshire
- ❌ 重复造轮子

### 2. 缺失商业模式分析
- ❌ 没有客户购买理由分析
- ❌ 没有盈利来源拆解
- ❌ 没有护城河分析
- ❌ 缺乏CEO/股东视角

### 3. 缺失动态发现能力
- ❌ 不能监控行业异动
- ❌ 不能分析"为什么涨"
- ❌ 不能找关联度高的公司
- ❌ 是静态工具，不是研究平台

### 4. 架构偏离设计
- ❌ 单股票分析工具
- ❌ 不是"指定对象研究 + 主动机会发现"平台
- ❌ 缺少研究编排器
- ❌ 缺少证据库

---

## 🎯 正确的实施路径

### Phase 1: 调研vendor目录（0.5天）
**任务**：
1. 研究luopan代码结构
   - 公司画像
   - 八指标初筛
   - 研究路由
2. 研究ai-berkshire代码结构
   - 基本面研究资产
   - 估值工作流
3. 制定集成方案

**输出**：
- vendor项目能力清单
- 集成适配器设计

---

### Phase 2: 实现商业模式分析（2天）

#### 2.1 数据结构设计
```python
BusinessModel {
  earnings_sources: [
    {
      product: str,
      revenue_share: float,
      profit_share: float,
      customer_type: str,
      purchase_reason: str,  # 客户为什么买
      system_layer: str,     # 核心/关键/重要/辅助
      criticality: str,      # 对客户的重要性
      unit_value: float,     # 单位价值
      switching_cost: str,   # 转换成本
    }
  ],
  moat: {
    type: str,              # 护城河类型
    strength: str,          # 强/中/弱
    sustainability: str,    # 可持续性
  },
  pricing_power: str,       # 定价能力
  cash_flow_model: str,     # 现金流模式
  capital_intensity: str,   # 资本密集度
}
```

#### 2.2 分析模块
```python
class BusinessModelAnalyzer:
    def analyze_earnings_sources(company)
    def analyze_customer_value(product)
    def analyze_moat(company)
    def analyze_pricing_power(company)
    def from_ceo_perspective(company)
    def from_shareholder_perspective(company)
```

---

### Phase 3: 集成luopan/ai-berkshire（3天）

#### 3.1 适配器设计
```python
class LuopanAdapter:
    """luopan能力适配器"""
    def get_company_profile(stock_code)
    def get_eight_indicators(stock_code)
    def route_research_flow(stock_code)

class AIBerkshireAdapter:
    """ai-berkshire能力适配器"""
    def get_fundamental_analysis(stock_code)
    def get_valuation_workflow(stock_code)
```

#### 3.2 能力复用
- 直接调用luopan的公司识别
- 复用ai-berkshire的研究资产
- 保留已有的产业链知识库

---

### Phase 4: 行业雷达与机会发现（2天）

#### 4.1 行业监控
```python
class IndustryRadar:
    def monitor_price_changes()       # 监控涨跌
    def analyze_why_rise()            # 分析为什么涨
    def find_related_companies()      # 找关联公司
    def rank_by_correlation()         # 按关联度排序
```

#### 4.2 机会发现
```python
class OpportunityDiscovery:
    def scan_undervalued()           # 扫描低估
    def scan_cycle_bottom()          # 扫描周期底部
    def scan_catalysts()             # 扫描催化剂
```

---

### Phase 5: 重构为平台架构（3天）

#### 5.1 研究编排器
```python
class ResearchOrchestrator:
    def research_single_stock(stock_code)
    def research_industry(industry)
    def discover_opportunities(criteria)
```

#### 5.2 证据库
```python
class EvidenceBase:
    def store_evidence(evidence)
    def query_evidence(stock_code)
    def trace_source(evidence_id)
```

---

## 📊 重构进度表

| Phase | 任务 | 时间 | 状态 |
|-------|------|------|------|
| 1 | 调研vendor目录 | 0.5天 | ⏳ |
| 2 | 商业模式分析 | 2天 | ⏳ |
| 3 | 集成luopan/ai-berkshire | 3天 | ⏳ |
| 4 | 行业雷达 | 2天 | ⏳ |
| 5 | 平台化重构 | 3天 | ⏳ |
| **总计** | | **10.5天** | |

---

## 🚀 立即开始

**第一步：调研vendor/luopan和vendor/ai-berkshire**

需要回答：
1. 它们提供什么能力？
2. 如何调用？
3. 如何集成？
4. 与现有系统如何结合？

---

**准备开始吗？**
