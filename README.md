# Industry First Research

行业先行投研系统：先发现行业，再建立行业公司池，最后对少量候选做深度研究和模拟决策记录。

本项目不自动交易、不连接券商账户，也不把任何模型回答当成事实。它的第一版核心是一个可复核、资源受控的本地研究编排器：

```text
行业雷达
  -> 少量行业候选
  -> 行业公司池
  -> 分层加载公司数据
  -> 少量公司深研
  -> 用户确认模拟决策
  -> 持有论文、跟踪和归因
```

## 当前状态

已完成：

- 行业优先机会发现的领域模型和资源策略；
- `cycle_reversal`、`quality_repair` 两类首期扫描器的接口；
- 本地 JSON 快照存储；
- 外部网页 AI 研究输入的人工粘贴协议；
- 可运行的测试和 CLI 演示。

尚未完成：

- AKShare、QMT、原始公告和行业数据的生产适配器；
- `luopan` / `ai-berkshire` 的字段级研究资产导入；
- 真实行业雷达数据源和产品级深研；
- Web 界面和微信公众号草稿发布。

## 开发

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
python -m industry_first_research demo
```

获取只读行业雷达快照：

```bash
PYTHONPATH=src python -m industry_first_research radar --source cross --limit 50
```

跨源行业名称映射使用版本化文件 `docs/industry_aliases.v1.json`，可通过
`--alias-file` 指定替代文件；映射错误会阻止交叉验证，不会自动模糊匹配。

获取选定行业的有限公司池：

```bash
PYTHONPATH=src python -m industry_first_research company-pool --industry-id 881145 --industry-name 电力 --limit 30
```

追加公开公司 LIGHT 资料：

```bash
PYTHONPATH=src python -m industry_first_research company-pool --industry-id 881145 --industry-name 电力 --limit 30 --with-light-data
```

`--with-light-data` first reads Tonghuashun LIGHT fields. When `listing_market` is
missing, it uses a bounded Eastmoney company-survey lookup and accepts the result only
when the returned company code matches. The field-level source is retained; no market is
inferred from the stock code.

运行行业到公司 LIGHT 资料的只读编排：

```bash
PYTHONPATH=src python -m industry_first_research discover --max-selected-industries 3 --company-pool-size 10
```

对公司池的 LIGHT 资料做只读完整度筛选：

```bash
PYTHONPATH=src python -m industry_first_research screen --input data/company_pools/tonghuashun-company-pool-881145-YYYY-MM-DD.json --expected-industry 电力
```

将候选队列与人工核验的补充证据合并为只读证据包：

```bash
PYTHONPATH=src python -m industry_first_research supplemental \
  --input data/candidate_queues/<queue>.json \
  --evidence data/supplemental_evidence/<records>.json \
  --required-field company_scope \
  --required-field reporting_scope \
  --required-field key_products \
  --required-field key_risks
```

For a field-level LIGHT gap, generate a blank manual evidence template first:

```bash
PYTHONPATH=src python -m industry_first_research evidence-template \
  --input data/candidate_queues/<queue>.json \
  --company-id 300317 \
  --field listing_market
```

The template does not assert a value. Manually verified records must retain the company,
field, source, date, evidence tier, and verification status. Empty values are rejected;
`listing_market` cannot be inferred from a stock code or market convention.

补充证据必须保留公司、字段、来源、日期、证据等级和核验状态。该步骤只生成
`READY/PARTIAL/INSUFFICIENT/BLOCKED` 覆盖状态，不自动升级候选、不生成估值，也不执行交易。

根据补充证据生成可研究性闸门：

```bash
PYTHONPATH=src python -m industry_first_research readiness \
  --input data/company_supplemental/<report>.json
```

`READY` 才能进入标准研究，`PARTIAL` 只能降级研究，`INSUFFICIENT` 只能初筛，
`BLOCKED` 暂停深度研究。该闸门保留原候选状态，不自动升级候选或生成投资结论。

生成只读快速研究快照：

```bash
PYTHONPATH=src python -m industry_first_research quick-research \
  --readiness data/company_readiness/<readiness>.json \
  --supplemental data/company_supplemental/<supplemental>.json
```

快速研究只整理已核验事实、未核验线索和资料缺口，不包含财务分析、估值或投资结论。

按设计文档继续生成产品与盈利来源画像的证据闸门：

```bash
PYTHONPATH=src python -m industry_first_research product-profile \
  --input data/company_supplemental/<supplemental>.json
```

该步骤只整理产品、应用、客户采购理由、系统层级、关键程度、替代关系、竞争对手、
市场状态、盈利来源、生命周期、客户验证和收入—利润—现金流桥接的证据覆盖；缺口不
会被自动补齐。只有 `READY` 才能进入后续应用传导、行业周期、生存、估值和决策模块。

产品画像 `READY` 后，继续建立产品到下游应用和终端市场的显式映射：

```bash
PYTHONPATH=src python -m industry_first_research application-mapping \
  --input data/company_product_profiles/<product-profile>.json
```

该步骤要求保留产品、应用、终端市场、需求驱动、客户验证、订单、出货/收入、供给
能力、竞争和需求传导状态的证据。没有 `product-profile` 的 `READY` 或没有明确的
产品—应用关系时，映射会被阻断或标为 `INSUFFICIENT`，不会推导风口收入、估值或投资结论。

应用映射 `READY` 后，继续检查风口需求是否传导到公司：

```bash
PYTHONPATH=src python -m industry_first_research demand-transmission \
  --input data/company_application_mappings/<application-mapping>.json
```

传导阶段严格区分 `CONCEPT_LINKED`、`TECHNICALLY_FEASIBLE`、`CUSTOMER_QUALIFIED`、
`ORDER_VALIDATED`、`REVENUE_VALIDATED`、`PROFIT_VALIDATED` 和
`COMPETITIVE_VALIDATED`。订单前的新业务只保留为上行期权，无法完成利润和现金流验证时
不得进入基准盈利、估值或投资结论。

历史快照达到至少 3 个日期后，可生成只读趋势报告：

```bash
PYTHONPATH=src python -m industry_first_research trend --source cross --min-observations 3
```

行业雷达使用东方财富和同花顺两个公开来源，只有同名行业且方向一致时才标记为
`CROSS_VALIDATED`，输出带日期、来源和证据状态的 `industry-radar.v1` JSON，并保存到
`data/radar/`。单日行情只作为行业强弱线索，不会自动确认周期反转，也不会连接券商或执行交易。详见
[`docs/industry-radar.md`](docs/industry-radar.md)。

也可以直接运行：

```bash
PYTHONPATH=src python -m industry_first_research demo
```

## 外部研究资产

本地 `vendor/luopan` 和 `vendor/ai-berkshire` 是用于开发和研究验证的上游工作树。由于本仓库是公开仓库，当前不自动提交其中的历史报告、数据和完整工作树；来源版本记录在 [`vendor/SOURCES.md`](vendor/SOURCES.md)。后续会通过适配器引用或按许可证明确允许的内容接入。

## 文档

- [`outputs/投研分析系统-需求文档.md`](outputs/投研分析系统-需求文档.md)
- [`outputs/投研分析系统-设计文档.md`](outputs/投研分析系统-设计文档.md)
- [`outputs/投研分析系统-评审记录-2026-07-17.md`](outputs/投研分析系统-评审记录-2026-07-17.md)
- [`docs/decisions/0002-external-ai-research-input.md`](docs/decisions/0002-external-ai-research-input.md)

网页 AI 说明：豆包、腾讯元宝、DeepSeek 等网页产品只通过 `MANUAL_WEB_AI` 模式人工导入。它们适合发现资料和提出反证，不进入自动行业雷达，也不能单独支撑关键事实、候选升级或模拟决策。

## 免责声明

本项目只生成研究辅助内容和模拟决策记录，不构成投资建议，不执行真实交易。用户应自行核验数据和承担研究、模拟操作及传播风险。
