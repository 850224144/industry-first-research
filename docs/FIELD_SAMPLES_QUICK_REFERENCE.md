# 真实字段样例快速参考

## 快速导航

| 数据源类型 | 样例文件 | 公司/品种 | 关键字段 |
|-----------|---------|----------|---------|
| **交易所公告** | | | |
| 上交所 | `official_exchange_sse_real.json` | 600519 贵州茅台 | document_id, publishDate, security_code |
| 深交所 | `official_exchange_szse_real.json` | 002594 比亚迪 | announcement_id, notice_date, code |
| **公司官网** | | | |
| 上市公司HTML | `company_disclosure_sse_real.html` | 600438 通威股份 | meta标签, document-id, publish-time |
| 公司披露HTML | `company_disclosure_szse_real.html` | 000858 五粮液 | meta标签, security-code |
| **东方财富** | | | |
| 季报公告 | `eastmoney_announcement_real_quarterly.json` | 300750 宁德时代 | art_code, notice_date, codes |
| 合同公告 | `eastmoney_announcement_real_contract.json` | 601012 隆基绿能 | art_code, notice_type |
| **期货交易所** | | | |
| 上期所库存 | `futures_exchange_shfe_inventory.html` | CU 铜 | variety, warehouse_receipts |
| 大商所规则 | `futures_exchange_dce_rules.html` | M 豆粕 | variety, margin_ratio |

## 数据源字段样例

| 类型 | 样例文件 | 主要字段 |
|-----|---------|---------|
| **期货数据** | | |
| 库存仓单 | `futures_exchange_inventory_detail.json` | exchange, variety, warehouse_receipts |
| 日结算 | `futures_exchange_daily_settlement.json` | contract, settlement, open_interest |
| **东方财富数据** | | |
| 财务摘要 | `eastmoney_financial_summary.json` | total_revenue, net_profit, roe |
| 公司资料 | `eastmoney_company_profile.json` | company_name, main_business, industry |
| **交易所行情** | | |
| 上交所 | `official_exchange_sse_quote.json` | symbol, close, market_cap |
| 深交所 | `official_exchange_szse_quote.json` | code, close, pe_ttm |
| **公司官网数据** | | |
| 投资者关系 | `company_website_investor_relations.json` | ir_contact, company_profile |
| 产品信息 | `company_website_product_info.json` | product_categories, products |

## 关键字段映射

### 公告类必需字段
- `document_id` / `announcement_id` / `art_code` - 公告编号
- `title` / `notice_title` / `announcement_title` - 标题
- `published_at` / `notice_date` / `publish_time` - 发布时间
- `subject_id` / `security_code` / `stock_code` - 证券代码
- `issuer` / `company_name` - 发行人

### 期货数据字段
- `exchange` - 交易所 (SHFE/DCE/CZCE/CFFEX/INE)
- `variety` - 品种代码 (CU/M/RB/SC等)
- `contract` - 具体合约 (CU2607)
- `settlement` - 结算价
- `open_interest` - 持仓量

### 财务数据字段
- `total_revenue` - 营业总收入
- `net_profit` - 净利润
- `roe` - 净资产收益率
- `total_assets` - 总资产
- `asset_liability_ratio` - 资产负债率

## 测试用例对应表

| 测试文件 | 测试用例数 | 覆盖样例 |
|---------|-----------|---------|
| `test_real_field_samples.py` | 11 | 8个公告样例 |
| `test_data_source_field_samples.py` | 11 | 8个数据源样例 |

## 使用场景

### 1. 验证新的解析器
```python
from industry_first_research.announcement_templates import parse_announcement_input

# 使用真实样例测试
raw = Path("tests/fixtures/announcements/official_exchange_sse_real.json").read_bytes()
report = parse_announcement_input(config, raw, template)
assert report["status"] == "READY"
```

### 2. 回归测试
```bash
# 验证所有样例解析正常
pytest tests/test_real_field_samples.py -v

# 验证特定数据源
pytest tests/test_data_source_field_samples.py::test_futures_exchange_inventory_detail_structure
```

### 3. 添加新样例
1. 复制真实数据到 `tests/fixtures/` 目录
2. 确保包含 `source_document_id` 字段
3. 在测试文件中添加测试用例
4. 运行测试验证

## 字段提取方法

| 方法 | 说明 | 示例 |
|-----|------|------|
| `json_path` | JSON路径提取 | `data.art_code` |
| `html_meta` | HTML meta标签 | `<meta name="document-id">` |
| `html_label` | HTML标签文本 | 正文中的"公告编号：xxx" |
| `regex` | 正则表达式匹配 | `公告编号\s*[:：]\s*(?P<value>[^\s]+)` |

## 常见问题

### Q: 为什么有些测试接受 DEGRADED 状态？
A: DEGRADED 表示核心字段解析成功，但某些可选字段缺失。这在真实场景中是正常的，不影响基本功能。

### Q: 如何处理字段名称差异？
A: 模板配置中包含多个候选路径，按优先级依次尝试：
```json
"subject_id": {
  "json_paths": ["codes", "security_code", "stock_code", "code"]
}
```

### Q: 时间戳格式要求？
A: 统一使用 ISO 8601 格式，包含时区信息：
- `2026-04-28T16:30:00+08:00`
- `2026-03-20 09:30:00` (自动转换)

## 文件路径

```
tests/
├── fixtures/
│   ├── announcements/          # 公告样例
│   │   ├── company_disclosure_*.html
│   │   ├── eastmoney_announcement_*.json
│   │   ├── futures_exchange_*.html
│   │   └── official_exchange_*.json
│   └── data_sources/           # 数据源样例
│       ├── company_website_*.json
│       ├── eastmoney_*.json
│       ├── futures_exchange_*.json
│       └── official_exchange_*.json
├── test_real_field_samples.py
└── test_data_source_field_samples.py

docs/
├── real_field_samples_supplement.md  # 详细说明
├── SUPPLEMENT_SUMMARY.md             # 工作总结
└── FIELD_SAMPLES_QUICK_REFERENCE.md  # 本文档
```

## 相关资源

- 公告模板配置: `config/announcement_templates.v1.json`
- 项目README: `README.md` (第59行提到此任务)
- 详细文档: `docs/real_field_samples_supplement.md`
