# 投研系统重新设计 v2.0 - 基于原始设计文档

## 📋 设计依据

基于以下原始文档：
- `outputs/投研分析系统-设计文档.md` (v0.14)
- `outputs/投研分析系统-需求文档.md` (v0.14)
- `outputs/投研分析系统-评审记录-2026-07-17.md`

## 🎯 核心理念（保留原设计）

### 原设计的正确方向
1. **行业优先** - 先找行业，再找公司
2. **分层加载** - 不要全市场扫描，按需加载数据
3. **证据驱动** - 每个结论都有来源和时间截面
4. **生存优先** - 不只看当前，更看能否活下来
5. **模拟决策** - 不自动交易，只提供建议

### 之前实现的问题
- ❌ 使用静态JSON而不是真实API
- ❌ 89个模块过度设计
- ❌ 没有真正的自动化流程

### 新设计的改进
- ✅ 真实API数据（AKShare等）
- ✅ 简化模块结构（保留核心概念）
- ✅ 自动化执行流程

---

## 🏗️ 新架构设计

### 层次结构

```
┌─────────────────────────────────────────────────────────┐
│                    用户入口层                             │
│  - CLI命令行                                             │
│  - (可选) 简单Web界面                                    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                 任务解析与路由层                          │
│                                                          │
│  1. TaskResolver (任务解析器)                           │
│     - 识别：公司/行业/期货/机会发现                      │
│     - 验证：代码/名称合法性                             │
│     - 路由：选择对应的研究编排器                        │
└────────────────────┬────────────────────────────────────┘
                     │
        ┌────────────┼────────────┬──────────────┐
        │            │            │              │
┌───────▼─────┐  ┌──▼────┐  ┌───▼──────┐  ┌───▼────────┐
│行业雷达     │  │公司    │  │期货      │  │机会发现    │
│研究         │  │研究    │  │研究      │  │            │
└─────────────┘  └────────┘  └──────────┘  └────────────┘
        │            │            │              │
        └────────────┼────────────┴──────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                   数据采集层                             │
│                                                          │
│  DataCollector (统一数据采集器)                         │
│    - AKShare (主要)                                     │
│    - 东方财富 (备用)                                     │
│    - BaoStock (历史)                                    │
│    - 交易所公告 (官方)                                   │
│                                                          │
│  功能:                                                   │
│    - 自动重试                                            │
│    - 多源切换                                            │
│    - 本地缓存                                            │
│    - 健康检查                                            │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                   存储层                                 │
│                                                          │
│  SQLite数据库                                           │
│    - 公司数据表                                          │
│    - 行业数据表                                          │
│    - 期货数据表                                          │
│    - 研究版本表                                          │
│    - 证据追溯表                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 📦 核心模块设计（简化版）

### 模块1: 任务解析器 (task_resolver.py)

```python
class TaskResolver:
    """
    任务解析器
    功能：识别用户输入，路由到对应研究流程
    """
    
    def resolve(self, user_input: str) -> ResearchTask:
        """
        解析用户输入
        
        支持:
        - 600021 → 公司研究
        - 电力行业 → 行业研究  
        - RU2609 → 期货研究
        - discover → 机会发现
        """
        pass
    
    def validate_identity(self, identifier: str) -> bool:
        """验证标识合法性"""
        pass
```

**关键原则**：
- 不猜测市场（600021不自动加.SH）
- 多个候选时要求用户确认
- 输出不可变的任务对象

### 模块2: 数据采集器 (data_collector.py)

```python
class DataCollector:
    """
    统一数据采集器
    实现原设计的"多源路由"概念
    """
    
    def __init__(self):
        self.sources = {
            'primary': AKShareAdapter(),
            'backup': EastMoneyAdapter(),
            'historical': BaoStockAdapter()
        }
        self.cache = LocalCache()
    
    def get_stock_data(self, code: str, retry=3) -> Dict:
        """
        获取股票数据（带重试和切换）
        
        流程：
        1. 尝试主源（AKShare）
        2. 失败则切换备源
        3. 缓存成功结果
        4. 记录健康状态
        """
        for source_name in ['primary', 'backup']:
            try:
                data = self.sources[source_name].fetch(code)
                self.cache.save(data)
                return data
            except Exception as e:
                self.log_failure(source_name, e)
                continue
        
        raise DataCollectionError("All sources failed")
    
    def get_industry_radar_data(self) -> Dict:
        """获取行业雷达数据"""
        pass
    
    def health_check(self) -> HealthReport:
        """数据源健康检查"""
        pass
```

**关键原则**：
- 主备切换自动化
- 记录数据来源和时间
- 失败不静默

### 模块3: 行业雷达 (industry_radar.py)

```python
class IndustryRadar:
    """
    行业雷达
    实现原设计的"行业优先"机会发现
    """
    
    def scan_industries(self) -> List[IndustrySignal]:
        """
        扫描行业信号
        
        不扫描全市场个股！
        只获取行业级数据：
        - 行业指数
        - 行业涨跌家数
        - 行业资金流向
        """
        industries = self.get_industry_list()
        
        signals = []
        for industry in industries:
            signal = self.analyze_industry(industry)
            if self.is_candidate(signal):
                signals.append(signal)
        
        return signals
    
    def analyze_industry(self, industry: str) -> IndustrySignal:
        """
        分析单个行业
        
        关键指标：
        - 需求趋势
        - 库存水平
        - 价格走势
        - 成本变化
        - 供给退出
        """
        pass
    
    def select_candidates(self, signals: List) -> List[str]:
        """
        选出候选行业（少数）
        
        原则：
        - 宁缺毋滥
        - 空集是合法结果
        - 保留淘汰理由
        """
        pass
```

**关键原则**：
- 行业级数据，不要个股数据
- 选出少数行业（3-5个）
- 记录选择和淘汰理由

### 模块4: 公司研究编排器 (company_researcher.py)

```python
class CompanyResearcher:
    """
    公司研究编排器
    实现原设计的10阶段分析管道（简化版）
    """
    
    def research(self, company_id: str) -> ResearchReport:
        """
        完整研究流程
        
        阶段（简化到5个核心阶段）：
        1. 身份与行业识别
        2. 财务健康分析
        3. 行业处境分析
        4. 生存能力分析
        5. 估值与建议
        """
        # 1. 识别
        identity = self.identify_company(company_id)
        
        # 2. 财务健康
        financial = self.analyze_financial(company_id)
        
        # 3. 行业处境
        industry = self.analyze_industry_situation(identity.industry)
        
        # 4. 生存能力
        survival = self.analyze_survival(financial, industry)
        
        # 5. 估值与建议
        valuation = self.valuate(financial, survival)
        
        return self.generate_report({
            'identity': identity,
            'financial': financial,
            'industry': industry,
            'survival': survival,
            'valuation': valuation
        })
    
    def analyze_survival(self, financial, industry):
        """
        生存能力分析
        
        关键问题（原设计核心）：
        - 行业长期低迷时能活下来吗？
        - 现金流能撑多久？
        - 债务压力如何？
        - 有融资能力吗？
        """
        pass
```

**关键原则**：
- 简化到5个核心阶段
- 保留原设计的核心概念
- 每个阶段有明确输出

### 模块5: 期货研究编排器 (futures_researcher.py)

```python
class FuturesResearcher:
    """
    期货研究编排器
    """
    
    def research(self, variety_code: str) -> FuturesReport:
        """
        期货研究流程
        
        阶段：
        1. 品种与合约识别
        2. 供需分析
        3. 库存与基差
        4. 价格情景
        5. 合约建议
        """
        pass
```

### 模块6: 报告生成器 (report_generator.py)

```python
class ReportGenerator:
    """
    报告生成器
    生成Markdown格式的研究报告
    """
    
    def generate(self, research_result: Dict) -> str:
        """生成Markdown报告"""
        return f"""
# {research_result['company_name']} 投资分析报告

生成时间：{datetime.now()}
数据来源：AKShare
研究版本：v{version}

## 1. 公司基本信息
{self.format_identity(research_result['identity'])}

## 2. 财务健康分析
{self.format_financial(research_result['financial'])}

## 3. 行业处境
{self.format_industry(research_result['industry'])}

## 4. 生存能力评估
{self.format_survival(research_result['survival'])}

## 5. 估值与投资建议
{self.format_valuation(research_result['valuation'])}

## 6. 风险提示
{self.format_risks(research_result)}

## 7. 跟踪指标
{self.format_tracking(research_result)}

---
数据截止：{research_result['as_of']}
证据ID：{research_result['evidence_ids']}
"""
```

---

## 💾 数据库设计

### 核心表结构

```sql
-- 公司数据表
CREATE TABLE companies (
    code TEXT PRIMARY KEY,
    name TEXT,
    industry TEXT,
    collected_at TIMESTAMP,
    data_source TEXT,
    data_json TEXT  -- 完整JSON数据
);

-- 研究版本表（关键！）
CREATE TABLE research_versions (
    version_id TEXT PRIMARY KEY,
    subject_id TEXT,
    subject_type TEXT,  -- company/industry/futures
    research_as_of TIMESTAMP,
    created_at TIMESTAMP,
    conclusion TEXT,
    evidence_ids TEXT,
    previous_version_id TEXT,  -- 版本链
    content_hash TEXT
);

-- 行业雷达表
CREATE TABLE industry_radar (
    snapshot_id TEXT PRIMARY KEY,
    snapshot_at TIMESTAMP,
    industries_json TEXT  -- 行业信号JSON
);

-- 数据源健康表
CREATE TABLE source_health (
    check_id TEXT PRIMARY KEY,
    checked_at TIMESTAMP,
    source_name TEXT,
    status TEXT,  -- OK/FAILED
    response_time REAL,
    error_message TEXT
);
```

---

## 🚀 使用场景

### 场景1：分析上海电力

```bash
$ python invest.py analyze 600021

正在解析任务...
✓ 识别为：上海电力 (600021)
✓ 行业：电力（公用事业）

正在采集数据...
✓ 实时行情（AKShare）
✓ 财务数据（AKShare）
✓ 行业数据（AKShare）

正在分析...
[1/5] 身份识别...完成
[2/5] 财务健康...完成  
[3/5] 行业处境...完成
[4/5] 生存能力...完成
[5/5] 估值建议...完成

生成报告...
报告已保存：reports/600021_20260810.md

=== 核心结论 ===
💡 防御型资产，适合长期配置
✓ 生存能力：强（公用事业属性）
✓ 现金流：充裕
✓ 股息率：4.5%
⚠️ 成长性有限

版本ID: v-600021-20260810-001
证据ID: ev-20260810-akshare-001
```

### 场景2：行业机会发现

```bash
$ python invest.py discover

行业雷达扫描中...
✓ 扫描30个行业

发现候选行业：

#1 光伏设备（拐点候选）
   信号：库存去化 + 价格筑底 + 产能退出
   
#2 电力（稳定）
   信号：需求增长 + 政策支持

本期无其他合格候选

是否深入研究光伏设备行业？(y/n)
```

### 场景3：更新研究

```bash
$ python invest.py update 600021

加载上一版本...
版本：v-600021-20260809-001

对比变化：
✓ 价格：5.20 → 5.23 (+0.58%)
✓ 行业处境：无变化
✓ 财务假设：无变化

结论：维持原判断
无需生成新版本
```

---

## 📂 文件结构

```
invest/
├── main.py                    # CLI入口
├── task_resolver.py           # 任务解析
├── data_collector.py          # 数据采集
├── industry_radar.py          # 行业雷达
├── company_researcher.py      # 公司研究
├── futures_researcher.py      # 期货研究
├── report_generator.py        # 报告生成
├── database.py               # 数据库操作
├── config.py                 # 配置
├── adapters/                 # 数据源适配器
│   ├── akshare_adapter.py
│   ├── eastmoney_adapter.py
│   └── baostock_adapter.py
├── db/
│   └── research.db           # SQLite数据库
└── reports/                  # 生成的报告
```

**总共不超过15个文件**

---

## 🎯 开发优先级

### Phase 1: 数据采集基础（2天）
- [ ] DataCollector实现
- [ ] AKShare适配器
- [ ] 本地缓存
- [ ] 数据库表结构

### Phase 2: 单个公司研究（2天）
- [ ] TaskResolver
- [ ] CompanyResearcher（简化版）
- [ ] ReportGenerator
- [ ] CLI基础命令

### Phase 3: 行业雷达（1天）
- [ ] IndustryRadar实现
- [ ] 行业级数据采集
- [ ] 候选筛选逻辑

### Phase 4: 期货研究（1天）
- [ ] FuturesResearcher
- [ ] 期货数据适配

### Phase 5: 完善（1天）
- [ ] 版本管理
- [ ] 健康检查
- [ ] 错误处理

---

## ✅ 与原设计的对应

| 原设计概念 | 新实现 | 说明 |
|-----------|--------|------|
| 行业优先机会发现 | IndustryRadar | ✅ 保留 |
| 分层加载 | 按需调用DataCollector | ✅ 保留 |
| 10阶段分析管道 | 简化到5阶段 | ⚠️ 简化但保留核心 |
| 多源路由 | DataCollector自动切换 | ✅ 保留 |
| 研究版本管理 | research_versions表 | ✅ 保留 |
| 证据追溯 | evidence_ids字段 | ✅ 保留 |
| 生存优先 | analyze_survival阶段 | ✅ 保留 |
| 模拟决策 | 报告输出，不执行 | ✅ 保留 |

---

## 🔑 关键改进

### 相比原实现
1. ✅ 真实API数据（不是静态JSON）
2. ✅ 自动化流程（可定时运行）
3. ✅ 简化架构（15文件 vs 89模块）

### 相比第一版极简设计
1. ✅ 保留原设计核心理念
2. ✅ 行业优先的机会发现
3. ✅ 研究版本和证据追溯
4. ✅ 分层加载数据

---

## 📖 下一步

这个设计：
- 基于原始设计文档的核心理念
- 解决静态数据问题
- 简化实现复杂度
- 保留可扩展性

**准备好开始实现了吗？**
