# 产业链知识库扩展设计方案

## 📊 当前状态

**已配置**：
- 4个行业（光伏、白酒、锂电池、半导体）
- 15家公司
- 手动配置

**问题**：
- 覆盖范围太小
- 无法自动更新
- 新增行业成本高

---

## 🎯 设计目标

### 1. 扩展性
- 支持30+主流行业
- 覆盖300+龙头公司
- 模块化配置

### 2. 自动化
- 自动识别公司所属产业链环节
- 自动更新产品重要性
- 基于实时数据调整评分

### 3. 维护性
- 配置与代码分离
- 支持JSON/YAML配置文件
- 版本化管理

---

## 🏗️ 架构设计

### 方案A：配置文件驱动（推荐）

```
industry_chains/
├── config/
│   ├── energy.yaml              # 能源行业
│   ├── photovoltaic.yaml        # 光伏
│   ├── battery.yaml             # 电池
│   ├── baijiu.yaml              # 白酒
│   ├── semiconductor.yaml       # 半导体
│   ├── auto.yaml                # 汽车
│   ├── pharmaceutical.yaml      # 医药
│   ├── consumer.yaml            # 消费
│   └── ... (30+行业)
│
├── knowledge_loader.py          # 配置加载器
├── auto_updater.py              # 自动更新器
└── validator.py                 # 配置验证器
```

**优点**：
- 非技术人员可编辑
- 易于版本控制
- 支持热更新

### 方案B：数据库驱动

```
SQLite/PostgreSQL
├── industries (行业表)
├── products (产品表)
├── companies (公司表)
├── product_companies (产品-公司关系表)
└── metadata (元数据表)
```

**优点**：
- 查询高效
- 支持复杂关系
- 易于管理

### 方案C：混合方案（最佳）

```
配置文件（静态知识）+ API数据（动态更新）
```

---

## 📝 配置文件格式

### YAML格式示例

```yaml
# photovoltaic.yaml
industry:
  name: "光伏设备"
  name_en: "Photovoltaic"
  category: "新能源"
  description: "光伏发电产业链"
  
chain:
  flow: "硅矿 → 工业硅 → 高纯硅料 → 硅片 → 电池片 → 组件 → 光伏电站 → 发电"
  stages:
    - name: "上游"
      segments: ["硅矿", "工业硅", "高纯硅料"]
    - name: "中游"
      segments: ["硅片", "电池片", "组件"]
    - name: "下游"
      segments: ["光伏电站", "发电运营"]

products:
  - name: "高纯硅料"
    level: "A"
    importance_score: 95
    value_ratio: 0.15
    value_ratio_desc: "占光伏组件总成本约15%"
    substitutability: "none"
    substitutability_desc: "硅基路线无替代品，钙钛矿等新技术尚未成熟"
    tech_barrier: "high"
    tech_barrier_desc: "高纯度要求（9个9以上），技术壁垒高"
    market_concentration: "high"
    market_concentration_desc: "全球前5家占70%+市场份额"
    analogy: "就像西红柿炒鸡蛋里的西红柿，没有就做不出这道菜"
    
  - name: "硅片"
    level: "B"
    # ... 其他配置

companies:
  - code: "600438"
    name: "通威股份"
    products: ["高纯硅料", "电池片"]
    position: "上游+中游"
    market_share: 0.12  # 可选，如果有精确数据
    
  - code: "601012"
    name: "隆基绿能"
    products: ["硅片", "电池片", "光伏组件"]
    position: "中游全产业链"

# 自动更新规则
auto_update:
  enabled: true
  indicators:
    - type: "market_concentration"
      source: "industry_comparison"
      update_frequency: "quarterly"
    - type: "tech_barrier"
      source: "manual"  # 需要人工判断
```

---

## 🤖 自动更新机制

### 1. 可自动更新的内容

#### 基于API数据
```python
# 自动更新项
- 市场集中度（根据行业对比实时计算）
- 价值占比（根据财报成本结构）
- 公司市场份额（根据营收排名）
- 产品重要性评分（综合多个指标）
```

#### 自动更新流程
```python
def auto_update_knowledge():
    """自动更新产业链知识"""
    
    # 1. 获取行业所有公司
    companies = get_industry_companies(industry)
    
    # 2. 计算市场集中度
    top5_share = sum(c['market_share'] for c in companies[:5])
    concentration = 'high' if top5_share > 0.6 else 'medium'
    
    # 3. 更新配置
    update_config('market_concentration', concentration)
    
    # 4. 重新计算产品评分
    recalculate_importance_score(product)
```

### 2. 需要人工维护的内容

```python
# 人工维护项（周期：年度）
- 产品等级（A/B/C/D）
- 技术路线变化
- 新产品/新技术出现
- "西红柿炒鸡蛋"类比
```

---

## 🚀 实施方案

### 阶段1：扩展配置文件（1-2周）

**目标**：覆盖20个主流行业

优先级列表：
1. 新能源：光伏✅、锂电池✅、风电、储能、氢能
2. 科技：半导体✅、消费电子、通信设备
3. 消费：白酒✅、食品饮料、医美、服装
4. 医药：创新药、医疗器械、CXO
5. 汽车：新能源车、智能驾驶、汽车零部件
6. 周期：煤炭、钢铁、化工、水泥

**工作量**：
- 每个行业：2-3小时研究 + 1小时配置
- 总计：40-80小时

### 阶段2：实现配置加载器（1-2天）

```python
# knowledge_loader.py
class IndustryKnowledgeLoader:
    """产业链知识加载器"""
    
    def __init__(self, config_dir='industry_chains/config'):
        self.config_dir = config_dir
        self.cache = {}
    
    def load_industry(self, industry_name: str) -> Dict:
        """加载行业配置"""
        # 从YAML文件加载
        
    def load_all(self) -> Dict:
        """加载所有行业"""
        
    def validate(self, config: Dict) -> bool:
        """验证配置正确性"""
```

### 阶段3：实现自动更新器（2-3天）

```python
# auto_updater.py
class KnowledgeAutoUpdater:
    """知识自动更新器"""
    
    def update_market_concentration(self, industry: str):
        """更新市场集中度"""
        # 基于实时行业数据计算
        
    def update_value_ratio(self, product: str):
        """更新价值占比"""
        # 基于财报成本结构分析
        
    def update_importance_score(self, product: str):
        """更新重要性评分"""
        # 综合多个指标重新计算
```

### 阶段4：版本化管理（1天）

```python
# 配置版本管理
industry_chains/
├── versions/
│   ├── v1.0_2026-08-12.json
│   ├── v1.1_2026-09-01.json
│   └── current -> v1.1_2026-09-01.json
```

---

## 📊 扩展后的覆盖范围

### 目标覆盖

| 类别 | 行业数 | 重点公司数 | 完成时间 |
|------|--------|------------|----------|
| 新能源 | 5 | 30 | 1周 |
| 科技 | 5 | 30 | 1周 |
| 消费 | 6 | 40 | 1.5周 |
| 医药 | 4 | 25 | 1周 |
| 汽车 | 4 | 30 | 1周 |
| 周期 | 6 | 30 | 1周 |
| **总计** | **30** | **185** | **6-8周** |

---

## 🛠️ 技术实现

### 配置模板生成工具

```python
# tools/generate_industry_template.py
def generate_industry_template(industry_name: str):
    """生成行业配置模板"""
    
    template = {
        'industry': {
            'name': industry_name,
            'description': '待补充',
        },
        'chain': {
            'flow': '待补充',
        },
        'products': [
            {
                'name': '待补充',
                'level': 'B',  # 默认B级
                'importance_score': 80,
                # ... 其他默认值
            }
        ],
        'companies': []
    }
    
    # 保存为YAML
    save_yaml(f'config/{industry_name}.yaml', template)
```

### 批量导入工具

```python
# tools/batch_import.py
def import_from_excel(file_path: str):
    """从Excel批量导入配置"""
    
    # Excel格式：
    # 行业 | 产品 | 等级 | 评分 | 公司代码 | 公司名称
    
    df = pd.read_excel(file_path)
    
    for industry in df['行业'].unique():
        config = generate_config_from_rows(
            df[df['行业'] == industry]
        )
        save_config(industry, config)
```

---

## 💡 智能化增强

### 1. 基于AI的辅助配置

```python
# 使用LLM辅助生成配置
def ai_assist_config(industry_name: str, company_name: str):
    """AI辅助生成产业链配置"""
    
    prompt = f"""
    分析{industry_name}行业中{company_name}的产业链位置：
    1. 主要产品是什么？
    2. 在产业链的什么环节？
    3. 产品重要性等级（A/B/C/D）
    4. 用"西红柿炒鸡蛋"类比
    """
    
    # 调用LLM API
    response = call_llm_api(prompt)
    
    # 转换为配置格式
    return parse_llm_response(response)
```

### 2. 基于新闻的动态更新

```python
def monitor_industry_news(industry: str):
    """监控行业新闻，识别变化"""
    
    news = get_industry_news(industry, days=7)
    
    # 识别关键事件
    events = extract_events(news)
    
    for event in events:
        if event.type == '新技术':
            alert('需要更新技术路线')
        elif event.type == '政策变化':
            alert('需要更新行业判断')
```

---

## 📋 优先级建议

### 立即实施（本周）
1. ✅ 设计配置文件格式
2. ✅ 创建模板生成工具
3. ⏳ 扩展5个新能源行业配置

### 短期（2-4周）
1. ⏳ 实现配置加载器
2. ⏳ 扩展到20个行业
3. ⏳ 实现基础自动更新

### 中期（1-2个月）
1. ⏳ 扩展到30个行业
2. ⏳ 实现智能更新机制
3. ⏳ 版本化管理

### 长期（3-6个月）
1. ⏳ AI辅助配置
2. ⏳ 新闻监控自动更新
3. ⏳ 开放社区贡献

---

## 🎯 推荐方案

**混合方案**：配置文件 + 自动更新 + AI辅助

**理由**：
1. 配置文件易于扩展和维护
2. 自动更新保证数据时效性
3. AI辅助降低配置成本
4. 分阶段实施，风险可控

**投入产出比**：
- 初期投入：2-3周
- 覆盖范围：4行业 → 20行业
- 长期收益：自动更新，零维护

---

**下一步：你想先实现哪个部分？**
1. 扩展配置文件（手工，但快速见效）
2. 实现配置加载器（技术基础）
3. AI辅助配置（降低扩展成本）
