# 天然橡胶（RU）商品适配器功能说明

## 概述

本次更新为行业先行投研系统新增了**天然橡胶（RU）**商品品种的完整支持，包括配置文件、测试数据和测试用例。

## 新增文件

### 1. 配置文件
- **位置**: `config/commodities/natural_rubber.json`
- **内容**: 天然橡胶产业链的完整配置
- **特性**:
  - 适配器 ID: `natural_rubber`
  - 交易所: SHFE（上海期货交易所）
  - 品种代码: `RU`
  - 商品类别: `agricultural_industrial`（农产品工业原料）

### 2. 测试 Fixture
- **基本面数据**: `tests/fixtures/commodities/natural_rubber_ru_fundamentals.json`
- **身份识别**: `tests/fixtures/commodities/identities/natural_rubber_ru2609_identity.json`

### 3. 测试用例
- 在 `tests/test_futures_cli_integration.py` 中新增 `test_natural_rubber_fundamentals_data_structure()`
- 更新 `test_all_fundamentals_have_evidence_traceability()` 和 `test_list_commodity_adapters()` 以包含天然橡胶

## 天然橡胶特有的数据字段

### 供需指标
- **生产数据**:
  - 中国、泰国、印度尼西亚等产区的产量
  - 割胶季节状态（旺季/淡季）
  - 种植面积

- **贸易数据**:
  - 中国进口量（按来源国分类）
  - 进口份额分析

- **需求数据**:
  - 轮胎产量（全钢胎+半钢胎）
  - 轮胎开工率
  - 汽车产量

### 库存与价格
- **库存位置**:
  - 港口库存（青岛港等）
  - 保税库存
  - 交易所仓单
  - 工厂库存
  - 经销商库存

- **现货基准**:
  - 华东天然橡胶现货
  - 青岛天然橡胶现货

### 成本与利润
- 泰国等主产区的生产成本
- 进口平价成本
- 经销商利润

### 季节性因素
- 割胶季节（5-9月旺季）
- 季风影响
- 轮胎替换季节
- 汽车销售周期
- 天气因素（降雨、温度、台风）

## 情景分析方法

天然橡胶使用 `supply_demand_inventory_and_seasonal_ranges` 方法，考虑：
- 割胶产量
- 进口量
- 轮胎需求
- 库存水平
- 季节性模式

## 验收样例

配置中定义了三个验收样例：
1. **合约就绪**: 合约、现货、产量、进口、库存、需求数据齐全
2. **季节性不完整**: 缺少割胶季节或气候因素时降级为待复核
3. **下游缺失**: 缺少轮胎或汽车产量时标记为需求证据不足

## 使用示例

### 列出所有商品适配器（包括天然橡胶）
```bash
PYTHONPATH=src python -m industry_first_research commodity-adapters \
  --directory config/commodities \
  --output-dir data/commodity_adapters
```

### 验证天然橡胶适配器配置
```bash
PYTHONPATH=src python -m industry_first_research commodity-adapter-validate \
  --directory config/commodities \
  --adapter natural_rubber \
  --output-dir data/commodity_adapter_validations
```

### 创建天然橡胶期货身份
```bash
PYTHONPATH=src python -m industry_first_research futures-identify \
  --input data/futures_inputs/ru2609_input.json \
  --output-dir data/futures_identities
```

### 生成天然橡胶基本面报告
```bash
PYTHONPATH=src python -m industry_first_research futures-fundamentals \
  --identity data/futures_identities/ru2609_identity.json \
  --input data/futures_inputs/ru_fundamentals.json \
  --output-dir data/futures_fundamentals
```

## 测试覆盖

所有测试均已通过：
- ✅ 配置文件验证
- ✅ 基本面数据结构验证
- ✅ 身份识别文件完整性
- ✅ 证据可追溯性
- ✅ 适配器注册表集成

```bash
# 运行天然橡胶相关测试
python -m pytest tests/test_futures_cli_integration.py::test_natural_rubber_fundamentals_data_structure -v
python -m pytest tests/verify_cli_pipeline.py::test_identity_files_completeness -v
```

## 系统状态

截至此次更新，系统现已支持 **6 个商品品种**：
1. 钢材（RB/HC） - 黑色系
2. 原油（SC） - 能源化工
3. 豆粕（M） - 农产品
4. 铜（CU/BC） - 有色金属
5. 碳酸锂（LC） - 新能源材料
6. **天然橡胶（RU）** - 农产品工业原料（新增）

## 后续建议

1. 添加真实的天然橡胶数据采集接口
2. 完善天然橡胶与轮胎公司的产品暴露连接
3. 增加天然橡胶季节性模式的历史回归测试
4. 添加天然橡胶与原油、合成橡胶的替代关系分析

## 相关文档

- [商品适配器配置说明](../config/commodities/README.md)
- [期货研究流程](../docs/futures-research-pipeline.md)
- [数据可追溯性](../docs/data-traceability.md)
