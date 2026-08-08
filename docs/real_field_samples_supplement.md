# 真实字段样例和解析回归样本补充说明

本次补充为四类数据源添加了真实字段样例和完整的解析回归测试。

## 补充的文件清单

### 1. 交易所公告样例（official_exchange）

#### 新增样例文件：
- `tests/fixtures/announcements/official_exchange_sse_real.json` - 上交所年报公告（贵州茅台）
- `tests/fixtures/announcements/official_exchange_szse_real.json` - 深交所重大合同公告（比亚迪）

#### 字段覆盖：
- 公告编号（document_id）
- 标题（title）
- 发布时间（publishDate/publish_time）
- 证券代码（security_code）
- 公司名称（company_name）
- 公告类型（notice_type）
- 附件信息（url, file_type, adjunct_size）
- 紧急标识（is_urgent）

### 2. 上市公司官网公告样例（company_disclosure）

#### 新增样例文件：
- `tests/fixtures/announcements/company_disclosure_sse_real.html` - 上市公司年报HTML（通威股份）
- `tests/fixtures/announcements/company_disclosure_szse_real.html` - 利润分配公告HTML（五粮液）

#### 字段覆盖：
- HTML meta标签提取（document-id, security-code, publish-time, issuer）
- HTML title提取
- 正文内容结构化
- 表格数据定位

### 3. 东方财富公告样例（eastmoney_announcement）

#### 新增样例文件：
- `tests/fixtures/announcements/eastmoney_announcement_real_quarterly.json` - 季报公告（宁德时代）
- `tests/fixtures/announcements/eastmoney_announcement_real_contract.json` - 重大合同公告（隆基绿能）

#### 字段覆盖：
- 公告编码（art_code）
- 公告标题（notice_title）
- 公告日期（notice_date）
- 证券代码（codes, security_code）
- 公司名称（company_name, security_name）
- 公告类型（notice_type）
- 分类栏目（column）
- PDF链接（pdf_url）
- 发布时间戳（publish_timestamp）
- 重要标识（important_flag）
- 批次编号（batch_num）
- 摘要信息（abstract）

### 4. 期货交易所公告样例（futures_exchange_disclosure）

#### 新增样例文件：
- `tests/fixtures/announcements/futures_exchange_shfe_inventory.html` - 上期所铜仓单数据
- `tests/fixtures/announcements/futures_exchange_dce_rules.html` - 大商所保证金调整规则

#### 字段覆盖：
- 公告编号（document-id）
- 品种代码（variety）
- 发布时间（publish-time）
- 发布单位（publisher）
- 标题（title）
- 数据表格（仓单明细、保证金比例）

## 数据源字段样例

### 5. 期货交易所数据样例

#### 新增样例文件：
- `tests/fixtures/data_sources/futures_exchange_inventory_detail.json` - 期货库存仓单详细数据（大商所豆粕）
- `tests/fixtures/data_sources/futures_exchange_daily_settlement.json` - 期货日结算数据（上期所铜）

#### 字段覆盖：
- 交易所（exchange）
- 品种信息（variety, variety_name, contract）
- 仓单数据（warehouse_receipts, prev_receipts, curr_receipts, change）
- 价格数据（pre_settlement, open, high, low, close, settlement）
- 交易数据（volume, open_interest, turnover）
- 合约规格（multiplier, tick_size, margin_ratio, trading_unit）
- 涨跌停板（limit_up, limit_down）
- 交割信息（last_trading_date, delivery_date）

### 6. 东方财富数据样例

#### 新增样例文件：
- `tests/fixtures/data_sources/eastmoney_financial_summary.json` - 财务数据摘要（通威股份）
- `tests/fixtures/data_sources/eastmoney_company_profile.json` - 公司基本资料（宁德时代）

#### 字段覆盖：
- 基本信息（security_code, security_name, report_date, report_type）
- 盈利能力（basic_eps, total_revenue, net_profit, roe, gross_profit_margin）
- 资产负债（total_assets, total_liabilities, net_assets, asset_liability_ratio）
- 现金流（operating_cash_flow, cash_flow_per_share）
- 运营效率（current_ratio, inventory_turnover, receivable_turnover）
- 公司详情（registered_capital, legal_representative, established_date, business_scope）
- 股本结构（total_shares, float_shares）
- 管理层信息（chairman, general_manager, secretary）

### 7. 交易所行情数据样例

#### 新增样例文件：
- `tests/fixtures/data_sources/official_exchange_sse_quote.json` - 上交所行情（贵州茅台）
- `tests/fixtures/data_sources/official_exchange_szse_quote.json` - 深交所行情（五粮液）

#### 字段覆盖：
- 基本信息（symbol/code, name, market, trade_date）
- 价格数据（open, high, low, close, pre_close, change, pct_change）
- 交易量（volume, amount, turnover/turnover_rate）
- 估值指标（pe_ttm/pe_ratio, pb/pb_ratio）
- 市值（total_market_value, float_market_value/circulating_market_cap）
- 时间戳（timestamp, update_time）

### 8. 上市公司官网数据样例

#### 新增样例文件：
- `tests/fixtures/data_sources/company_website_investor_relations.json` - 投资者关系信息（隆基绿能）
- `tests/fixtures/data_sources/company_website_product_info.json` - 产品信息（比亚迪）

#### 字段覆盖：
- 公司基本信息（company_code, company_name, company_name_en, website）
- 投资者关系联系人（ir_contact: department, secretary, email, phone, address）
- 公司简介（brief, established, listing_date, main_business, core_products）
- 生产基地（production_bases）
- 产品分类（product_categories, sub_categories, products）
- 产品详情（model, type, price_range, battery_capacity, range, features）

## 测试文件

### 新增测试文件：

#### 1. `tests/test_real_field_samples.py`
测试公告模板对真实字段样例的解析能力，包含：
- 11个测试用例
- 覆盖4类数据源的8个样例文件
- 验证字段定位器（field_locators）
- 验证内容哈希一致性
- 验证不同编码格式的支持

#### 2. `tests/test_data_source_field_samples.py`
测试数据源字段的结构完整性，包含：
- 11个测试用例
- 覆盖8个数据源样例文件
- 验证字段完整性
- 验证source_document_id一致性
- 验证数值类型和时间戳格式

## 测试结果

所有22个测试用例全部通过：
```
tests/test_real_field_samples.py ...........              [ 50%]
tests/test_data_source_field_samples.py ...........       [100%]
============================== 22 passed in 0.07s ==========================
```

## 字段样例特点

### 1. 真实性
所有字段名称和结构都基于实际交易所、公司官网、第三方数据平台的真实格式。

### 2. 完整性
每个样例包含：
- 所有必需字段（source_url, subject_type, subject_id, title, published_at）
- 可选字段（document_type, issuer, correction_status等）
- 来源追溯字段（source_document_id）
- 时间戳字段（ISO 8601格式）

### 3. 可回归性
- 所有样例文件固定不变
- 测试用例验证解析结果的一致性
- 支持字段定位器血缘追踪

### 4. 多格式支持
- JSON格式：交易所API响应、第三方平台API
- HTML格式：公司官网公告、交易所网页
- 混合格式：HTML meta标签 + JSON结构化数据

## 下一步扩展建议

1. **更多交易所**：北交所、港交所的公告样例
2. **更多数据类型**：公司公告中的定增、配股、重组等类型
3. **更多期货品种**：能源化工、农产品、有色金属等品种的数据样例
4. **异常情况处理**：更正公告、撤回公告、字段缺失等边界情况

## 使用说明

### 运行测试
```bash
# 运行所有新增测试
python -m pytest tests/test_real_field_samples.py tests/test_data_source_field_samples.py -v

# 运行特定测试
python -m pytest tests/test_real_field_samples.py::test_official_exchange_sse_annual_report_real_fields -v

# 运行数据源字段测试
python -m pytest tests/test_data_source_field_samples.py::test_futures_exchange_inventory_detail_structure -v
```

### 添加新样例
1. 在 `tests/fixtures/announcements/` 或 `tests/fixtures/data_sources/` 添加样例文件
2. 确保包含所有必需字段
3. 在相应测试文件中添加测试用例
4. 运行测试验证解析正确性

## 贡献者

本次补充完成了项目README第59行提到的下一阶段任务：
> 更多交易所和上市公司站点的字段样例与解析回归样本

补充内容涵盖：
- 8个公告样例文件
- 8个数据源字段样例文件
- 2个完整的测试文件
- 22个测试用例
- 本说明文档
