# 产业链知识库扩展实施方案 - 基于调研结果

## 📊 调研结论

### 核心发现
1. **AKShare已是最佳底座** - 无需替换，需深度利用
2. **腾讯产业链知识图谱方案提供最佳结构** - 用作数据模型参考
3. **真正缺失的是产品级产业链数据** - 不是技术框架

---

## 🎯 实施方案（基于免费优先）

### 阶段1：深度利用AKShare（本周）

#### 1.1 补充AKShare数据采集
```python
# 新增采集项
- stock_industry_category_cninfo()  # 多套行业分类
- stock_board_industry_name_em()    # 东方财富行业板块
- stock_board_industry_cons_em()    # 行业成分股
- stock_zyjs_ths()                  # 公司主营业务
```

#### 1.2 生成security_master快照
```python
# 全A股公司主表
- 股票代码、名称
- 所属行业（证监会/申万/中证/东财）
- 主营业务
- 更新时间
```

---

### 阶段2：参考腾讯方案优化数据模型（3-5天）

#### 当前问题
```python
# 现在：硬编码字符串
chain_flow = "硅矿 → 工业硅 → 高纯硅料 → 硅片 → 电池片"
```

#### 改进方案
```python
# 改为：结构化关系
product_relations = [
    {'from': '硅矿', 'to': '工业硅', 'relation': 'upstream'},
    {'from': '工业硅', 'to': '高纯硅料', 'relation': 'upstream'},
    ...
]
```

#### 新数据模型
```python
# 参考腾讯方案的表结构
products/
├── product.json              # 产品主表
├── product_relation.json     # 产品上下游关系
├── company_product.json      # 公司-产品映射
└── metadata.json             # 数据来源、版本、置信度
```

---

### 阶段3：数据来源优先级（渐进式）

#### 免费来源（立即实施）
1. **AKShare** - 公司、行业、财务数据 ✅
2. **官方分类** - 证监会/申万/中证行业分类 ⏳
3. **公开研报** - 券商产业链图谱（手工提取）⏳
4. **公司公告** - 年报主营业务、产品描述 ⏳

#### 商业来源（可选）
5. **数库科技/知数** - 产业链数据（如有预算）
6. **CSMAR** - 供应商-客户关系（如有高校资源）
7. **Wind/Choice** - 行业指标、市场份额（如有预算）

---

## 🛠️ 立即实施的具体步骤

### Step 1: 增强AKShare数据采集（今天）

```python
# research_system/akshare_enhanced.py
class AKShareEnhanced:
    """增强的AKShare数据采集"""
    
    def get_all_industries(self):
        """获取所有行业分类"""
        # 证监会分类
        csrc = ak.stock_industry_category_cninfo(symbol="证监会行业分类")
        
        # 申万分类
        sw = ak.stock_industry_category_cninfo(symbol="申银万国行业分类")
        
        # 中证分类
        csi = self._get_csi_industry()
        
        # 东方财富分类
        em = ak.stock_board_industry_name_em()
        
        return {
            'csrc': csrc,
            'sw': sw,
            'csi': csi,
            'em': em
        }
    
    def get_company_main_business(self, stock_code):
        """获取公司主营业务"""
        # 同花顺主营业务
        return ak.stock_zyjs_ths(symbol=stock_code)
    
    def generate_security_master(self):
        """生成全A股公司主表快照"""
        all_stocks = ak.stock_zh_a_spot_em()
        
        master = []
        for _, stock in all_stocks.iterrows():
            code = stock['代码']
            master.append({
                'code': code,
                'name': stock['名称'],
                'industry_em': self._get_industry(code, 'em'),
                'industry_sw': self._get_industry(code, 'sw'),
                'main_business': self.get_company_main_business(code),
                'update_time': datetime.now().isoformat(),
            })
        
        # 保存为JSON快照
        save_json('data/security_master.json', master)
        return master
```

### Step 2: 重构产业链数据模型（明天）

```python
# research_system/industry_chain_v2.py
class IndustryChainV2:
    """产业链知识库 V2 - 参考腾讯方案"""
    
    def __init__(self):
        self.products = self.load_json('data/products.json')
        self.product_relations = self.load_json('data/product_relations.json')
        self.company_products = self.load_json('data/company_products.json')
    
    def get_upstream_products(self, product_name):
        """获取上游产品"""
        return [r['from'] for r in self.product_relations 
                if r['to'] == product_name and r['relation'] == 'upstream']
    
    def get_downstream_products(self, product_name):
        """获取下游产品"""
        return [r['to'] for r in self.product_relations 
                if r['from'] == product_name and r['relation'] == 'downstream']
    
    def get_product_chain(self, product_name):
        """获取完整产业链"""
        # 递归获取上下游
        upstream = self._get_chain_recursive(product_name, 'upstream')
        downstream = self._get_chain_recursive(product_name, 'downstream')
        
        return {
            'upstream': upstream,
            'current': product_name,
            'downstream': downstream
        }
```

### Step 3: 数据格式标准化（2-3天）

```json
// data/products.json
[
  {
    "id": "prod_001",
    "name": "高纯硅料",
    "name_en": "Polysilicon",
    "industry": "光伏设备",
    "level": "A",
    "importance_score": 95,
    "value_ratio": 0.15,
    "substitutability": "none",
    "tech_barrier": "high",
    "analogy": "西红柿",
    "source": "manual",
    "confidence": 0.95,
    "version": "v1.0",
    "update_time": "2026-08-12"
  }
]

// data/product_relations.json
[
  {
    "from": "工业硅",
    "to": "高纯硅料",
    "relation": "upstream",
    "strength": "strong",
    "source": "industry_report",
    "confidence": 0.9
  }
]

// data/company_products.json
[
  {
    "stock_code": "600438",
    "stock_name": "通威股份",
    "products": ["高纯硅料", "电池片"],
    "position": "上游+中游",
    "source": "company_annual_report",
    "evidence": "2023年年报第XX页",
    "update_time": "2026-08-12"
  }
]
```

### Step 4: 数据导入工具（2天）

```python
# tools/import_industry_chain.py
class IndustryChainImporter:
    """产业链数据导入工具"""
    
    def import_from_research_report(self, pdf_path):
        """从研报提取产业链"""
        # 1. 解析PDF
        # 2. 识别产业链图谱
        # 3. 提取产品和关系
        # 4. 生成标准JSON
        pass
    
    def import_from_excel(self, excel_path):
        """从Excel导入"""
        # Excel格式：
        # 产品 | 上游产品 | 下游产品 | 等级 | 评分 | ...
        pass
    
    def validate_and_save(self, data):
        """验证并保存数据"""
        # 验证数据完整性
        # 检查关系闭环
        # 保存到JSON文件
        pass
```

---

## 📋 本周工作清单

### Day 1-2: 增强数据采集
- [x] 设计方案
- [ ] 实现AKShareEnhanced
- [ ] 生成security_master快照
- [ ] 测试多套行业分类

### Day 3-4: 重构数据模型
- [ ] 设计JSON格式
- [ ] 实现IndustryChainV2
- [ ] 迁移现有4个行业数据
- [ ] 编写单元测试

### Day 5: 数据导入工具
- [ ] 实现Excel导入
- [ ] 创建导入模板
- [ ] 编写使用文档

---

## 🎯 近期目标

### 1个月内
- ✅ 深度利用AKShare（全A股+行业分类）
- ✅ 重构产业链数据模型
- ⏳ 扩展到15个行业（从4个）
- ⏳ 覆盖100家公司（从15家）

### 3个月内
- ⏳ 扩展到30个行业
- ⏳ 覆盖300家公司
- ⏳ 整合公开研报数据
- ⏳ 实现自动更新机制

---

## 💰 成本效益分析

### 免费方案（推荐先实施）
- **成本**: 0元 + 开发时间1-2周
- **覆盖**: 全A股 + 15-30行业
- **维护**: 每月2-4小时

### 商业数据（如有预算）
- **数库科技**: 约5-10万/年，快速覆盖
- **CSMAR**: 高校免费，企业约3-5万/年
- **Wind/Choice**: 约3-5万/年/席位

---

## ✅ 与你的分析一致的地方

1. ✅ **AKShare是底座**，不替换，深度利用
2. ✅ **腾讯方案是结构参考**，不直接导入数据
3. ✅ **产品级产业链是缺口**，这是要补的核心
4. ✅ **不引入重复系统**，专注数据补充
5. ✅ **免费优先**，有预算再考虑商业数据

---

**下一步：立即实施Step 1（增强AKShare数据采集），要开始吗？**
