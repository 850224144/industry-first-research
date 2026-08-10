# 投研系统重新设计 - API优先架构

## 🎯 核心目标

**做一个真正有用的投研助手，不是展示静态数据的网页**

## 💡 设计原则

1. **API优先** - 所有数据来自真实API
2. **极简架构** - 只保留必要功能
3. **自动化** - 能自动运行的不要手动
4. **可验证** - 每个功能都能验证效果

---

## 🏗️ 新架构设计

```
┌─────────────────────────────────────────┐
│           用户界面                       │
│  - 简单的CLI命令                        │
│  - (可选) 极简Web查看                   │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│         核心功能 (3个)                   │
│                                         │
│  1. 数据采集 (DataCollector)            │
│     - AKShare API                      │
│     - 股票/指数/期货                    │
│     - 自动重试和缓存                    │
│                                         │
│  2. 简单分析 (SimpleAnalyzer)           │
│     - 财务指标计算                      │
│     - 基本面判断                        │
│     - 风险提示                          │
│                                         │
│  3. 报告生成 (ReportGenerator)          │
│     - Markdown报告                     │
│     - 关键指标展示                      │
│     - 投资建议                          │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│         数据存储                         │
│  - SQLite本地数据库                     │
│  - 历史数据版本                         │
│  - 简单清晰                             │
└─────────────────────────────────────────┘
```

---

## 📦 极简模块设计

### 1. 数据采集器 (data_collector.py)

```python
class DataCollector:
    def get_stock_realtime(self, code):
        """从AKShare获取实时行情"""
        pass
    
    def get_stock_financial(self, code):
        """获取财务数据"""
        pass
    
    def save_to_db(self, data):
        """保存到SQLite"""
        pass
```

**功能**：
- 调用AKShare API
- 自动重试（网络失败）
- 本地缓存（避免重复请求）
- 存储到SQLite

### 2. 简单分析器 (simple_analyzer.py)

```python
class SimpleAnalyzer:
    def analyze_stock(self, stock_data):
        """分析股票"""
        # 计算关键指标
        roe = ...
        debt_ratio = ...
        
        # 简单判断
        if roe > 15 and debt_ratio < 60:
            return "优质公司"
        
        return analysis_result
```

**功能**：
- 计算财务指标
- 简单规则判断（不要复杂模型）
- 输出清晰结论

### 3. 报告生成器 (report_generator.py)

```python
class ReportGenerator:
    def generate_markdown(self, analysis_result):
        """生成Markdown报告"""
        return f"""
        # {stock_name} 投资分析
        
        ## 基本信息
        - 当前价格: {price}
        - 市盈率: {pe}
        
        ## 财务分析
        - ROE: {roe}
        - 负债率: {debt_ratio}
        
        ## 投资建议
        {recommendation}
        """
```

**功能**：
- 生成Markdown报告
- 清晰的结构
- 可直接阅读

---

## 🚀 使用场景

### 场景1：分析单个股票

```bash
$ python invest.py analyze 600021

正在获取上海电力(600021)数据...
✓ 实时行情获取成功
✓ 财务数据获取成功
✓ 分析完成

=== 上海电力 投资分析 ===

基本信息:
  价格: 5.23元 (+0.58%)
  市盈率: 12.5
  市净率: 1.2

财务健康:
  ROE: 8.5% (公用事业正常水平)
  负债率: 65% (合理)
  现金流: 充裕

投资建议:
  💡 防御型资产，适合长期配置
  ✓ 稳定分红
  ⚠️ 成长性有限

报告已保存: reports/600021_20260810.md
```

### 场景2：定时监控

```bash
$ python invest.py watch 600021 --daily

已添加到监控列表，每天9:30自动分析
```

### 场景3：查看历史

```bash
$ python invest.py history 600021

历史分析记录:
  2026-08-10: 防御型资产 (价格: 5.23)
  2026-08-09: 防御型资产 (价格: 5.20)
  2026-08-08: 防御型资产 (价格: 5.18)
```

---

## 📂 文件结构（极简）

```
research_system/
├── invest.py              # 主入口（CLI）
├── data_collector.py      # 数据采集
├── simple_analyzer.py     # 简单分析
├── report_generator.py    # 报告生成
├── config.py             # 配置
├── database.py           # SQLite操作
├── requirements.txt      # 依赖（akshare, sqlite3）
└── reports/              # 生成的报告
```

**总共7个文件，不要更多！**

---

## 🎯 开发步骤

### Step 1: 数据采集（1天）
- 实现AKShare API调用
- 添加重试和缓存
- 存储到SQLite

### Step 2: 简单分析（1天）
- 财务指标计算
- 基本规则判断
- 输出清晰结论

### Step 3: CLI界面（0.5天）
- 主命令入口
- analyze/watch/history命令
- 友好的输出

### Step 4: (可选) Web界面（0.5天）
- 超简单的Flask界面
- 只用来查看报告
- 不要复杂功能

---

## ✅ 验收标准

**必须能做到**：
1. ✓ 输入股票代码，获取真实数据
2. ✓ 自动计算关键指标
3. ✓ 给出明确的投资建议
4. ✓ 生成可阅读的报告
5. ✓ 可以定时自动运行

**不需要**：
- ❌ 复杂的10阶段分析管道
- ❌ 89个模块
- ❌ 过度抽象的设计
- ❌ 静态测试数据

---

## 💭 为什么这样设计？

### 1. API优先
所有数据从AKShare等API获取，没有静态JSON

### 2. 极简架构
只有3个核心模块，容易理解和维护

### 3. 实用导向
CLI命令直接可用，不需要复杂配置

### 4. 可扩展
虽然简单，但可以逐步添加功能

---

## 🚀 现在开始实现？

我可以立即开始实现这个新设计。

你觉得这个方向对吗？需要调整什么？
