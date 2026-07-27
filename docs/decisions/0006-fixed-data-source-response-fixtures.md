# 决策记录 0006：免费数据源固定响应夹具

## 状态

已决定，2026-07-27 生效。

## 背景

交易所/公司披露、东方财富、AKShare 和 BaoStock 的接口可能受网络、限流、字段变化和可选依赖影响。
如果测试直接访问远端，主备路由、时间截面和数据刷新结果就无法稳定复现，也会把“今天接口可用”误当成
适配器协议正确。

## 决策

采用版本化本地固定响应夹具验证来源适配器和主备路由。夹具只模拟已知的返回形态，不宣称远端当前可达，
不进入正式证据层，不生成投资结论。

夹具覆盖：

- 交易所/公司披露 JSON 响应；
- 东方财富聚合行情 JSON 响应；
- AKShare endpoint 记录列表；
- BaoStock 登录、查询和历史记录结果；
- 主来源失败后备用来源成功；
- 空结果、字段不足、依赖缺失和刷新行数边界。

## 实现边界

- 夹具位于 `tests/fixtures/data_sources/`，测试通过模块替身或固定响应对象注入，不调用网络；
- `DataSourceRouter` 仍按交易所/公司披露、东方财富、AKShare、BaoStock 的配置顺序执行；
- `data-source-refresh.v1` 端到端夹具必须保留最终来源、失败尝试、稳定数据哈希和本地校验结果；
- 真实远端健康检查与固定夹具回归分开，不互相替代；
- 夹具变更必须更新来源形态说明和测试，不能把当前接口临时响应覆盖成无版本的“黄金文件”。

## 当前证据

- `tests/fixtures/data_sources/official_exchange_disclosure.json`
- `tests/fixtures/data_sources/eastmoney_quote.json`
- `tests/fixtures/data_sources/akshare_history.json`
- `tests/fixtures/data_sources/baostock_history.json`
- `tests/test_data_sources.py`
- `tests/test_data_refresh.py`

本决策不改变真实数据源的许可、接口条款或可用性审查；它只提高本地路由、边界和刷新协议的可复现性。
