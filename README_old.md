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
- `cycle_reversal`、`quality_repair`、`demand_acceleration`、`bottleneck_pricing` 四类机会扫描器的接口与保守初筛规则；
- 本地 JSON 快照存储；
- 外部网页 AI 研究输入的人工粘贴协议；
- 可运行的测试和 CLI 演示。
- 白酒行业配置化纵向切片：行业雷达、13 家代表公司池、5 家深度层、Markdown/HTML 报告和 JSON 快照。
- 确定性的周期反转/质量修复规则审计，以及公司淘汰、空结果和研究资产缺失留痕。
- 交易所/公司披露、东方财富、AKShare、BaoStock 的可插拔适配器和主备路由；连接失败、超时、限流、空结果或字段不完整会自动切换并保留尝试记录。
- 通威股份 `600438.SH` 公司研究配置化纵向切片：公司身份、业务范围、产品画像、财务和行情按字段主备采集，并输出 `READY/PARTIAL/INSUFFICIENT` 状态。
- 通用 `industry-radar` 行业信号采集命令：逐指标复用主备路由，保存来源尝试链，并明确公司池尚未加载。
- 统一 `SourceDocument`、`Evidence`、`ModelAssumption`、`ResearchArtifact`、候选集和评分卡对象：保存来源、发布时间、研究截止日、内容哈希、字段定位和字段级血缘。
- 多源证据截止日校验与冲突裁决：未来信息不回填历史，冲突值不简单平均，无法裁决时保留冲突并降级。
- 研究请求、QUICK/STANDARD/DEEP 深度路由、LOCAL_ONLY/LLM_ASSISTED/MANUAL_WEB_AI 执行模式及模型调用 Token/成本审计；模型不可用或预算耗尽时保留本地确定性路径。
- 公司边界 `CompanyScopeObject`：区分上市主体、合并集团、子公司、联营/合营、未并表业务和关联方，逐条绑定产品、订单、产能、收入、利润、现金与债务归属，并输出 `READY/PARTIAL/INSUFFICIENT/BLOCKED`。
- 来源锁定的 `MarketDataSnapshot`：固定来源版本、交易所/市场、复权、交易日历、截止日、原始文件哈希、缺失状态和公司行动；连续期货序列固定真实合约、主力和换月规则，不能直接作为模拟成交对象。
- 版本化市场注册表：固定市场/交易所、资产类别、币种、时区、交易日历和价格/公司行动约定；行情快照可锁定注册表版本和哈希。
- 不可变研究版本清单：统一记录研究时点、上一版本、管线/证据/行情引用、受影响模块、执行模式、规则版本和内容哈希；支持校验、对比和无网络 LOCAL_ONLY 回放准备。
- `data-source-health.v1` 数据源健康快照：检查适配器/可选依赖、能力和主备路由，保留不可用原因；调度任务和研究版本记录健康快照引用。
- 统一本地任务解析器：把公司、行业、期货、机会发现和论文检查输入归一为安全任务对象；身份不确定时进入待确认，不从裸代码推断上市市场。
- 版本化公告模板与本地解析器：提供交易所、公司披露、东方财富公告和期货交易所四类模板，支持 JSON/HTML/文本快照，记录字段定位、解析版本、原文哈希、纠正/撤回链和失败降级，不自动联网。
- 产品级收入—利润—现金流桥接：按基准/上行/下行场景保存销量、单价、成本、费用、营运资金和资本开支假设，保留区间和分摊口径；缺失或不可分摊时降级，不自动纳入公司预测。
- 产品生命周期与市场状态快照：显式记录导入/放量/成熟/降价/替代风险阶段、下一阶段条件、替代因素及价格/库存/供需/开工/客户资本开支/竞争扩产字段，不从价格自动推导阶段。
- 确定性财务模型：计算显式财务事实的利润率、现金转换、自由现金流、营运资金、现金跑道、债务缺口和三情景估值观察值；缺项不默认填充，不生成目标价。
- 第三方基础组件可选适配层：注册许可证、版本、依赖、Mac 可用性和回退方案；支持 `pypdf`/`pdfplumber`/`Camelot` 的本地 PDF 提取候选，以及 `quantstats` 优先、本地回退的收益统计；组件缺失不影响核心研究链路。
- 具体期货合约模拟结算账本：支持逐日盯市、当日保证金率、显式移仓、手续费/滑点、涨跌停阻断、保证金调用和模拟强平；与股票全额资金组合分开，不自动换月、不追加真实资金、不发送委托。
- 期货回放已接入统一归因和研究质量评分卡回归：保留保证金口径，不与股票全额资金收益直接相减，并将期货结果表现与事实/状态/模型质量分开评价。
- 行业适配器配置已扩展到 7 类：通用、周期制造、消费品牌、金融服务、软件/SaaS、医药健康和公用事业；金融服务、公用事业等非物理周期行业不会生成库存/产能周期模型。
- 商品品种适配器配置已覆盖黑色、能源化工、农产品、有色和新能源材料 5 类，支持 `RB`/`HC`、`SC`、`M`、`CU`/`BC`、`LC`、`RU`；当前只完成配置契约、目录解析和字段验收，不抓取数据、不产生方向结论。
- 期货刷新结果已可按显式品种映射转换为 `futures-fundamentals-input.v1`：转换保留刷新哈希、来源、查询 ID、数据哈希和字段路径，映射值默认标为 `UNVERIFIED`，必须经过人工证据闸门后才能进入正式基本面报告。
- 期货持续跟踪已接入：按交易所/品种/对象类型/具体合约比较已保存的基本面报告，生成不可变变化清单、受影响模块和 `decision_review` 人工复核投影，并关联研究版本；没有历史快照时只输出 `INITIALIZED`/待复核，不产生方向结论。
- 公开稿最小链路已接入：`public-draft` 从显式哈希锁定的公司/期货报告生成脱敏 Markdown 与 `public-draft.v1` JSON，`validate-public-draft` 校验正文哈希和未发布边界；不联网、不登录、不调用微信公众号接口。
- 有界数据源刷新已接入：`data-refresh` 只执行显式 `data-source-refresh-input.v1` 查询清单，按交易所/公司披露、东方财富、AKShare、BaoStock 主备路由保存实际返回、失败尝试、截断状态、来源健康、受影响模块、`decision_review` 和研究版本；不配置清单时不发网络请求。
- 本地 Web 研究控制台已接入：`web` 提供快照索引、状态概览和任务解析入口，默认绑定 `127.0.0.1`；只读读取已保存元数据，任务解析可保存不可变任务，不抓取行情、不调用模型、不创建决策快照或发布内容。
- 增量更新已支持安全的下游局部重算：新增原始证据从 `product_profile` 开始，独立市场结构更新可复用上游阶段从 `adversarial_review` 开始；每次结果保存 `recompute_plan`，不会复用含有新证据的旧阶段。
- 公司研究报告已增加 `simulation_recommendation` 工作流投影：资料不足时等待/观察，证据齐备时进入用户确认；不生成买卖指令、目标价或决策快照。

下一阶段：

- 更多交易所和上市公司站点的字段样例与解析回归样本；当前四类模板已建立协议和本地解析入口；
- 更多商品品种配置、各品种真实数据链路回归和完整报告字段回归；
- Web 界面和微信公众号草稿发布。

### 公司边界与行情快照

深度研究前先建立公司范围。公司的产品、订单和财务事实必须绑定到上市主体、合并集团、子公司、联营/合营、未并表业务或关联方之一；参股公司的订单和产能不会因为概念标签自动归属于上市公司。

```bash
PYTHONPATH=src python -m industry_first_research company-scope \
  --input config/company_scope_input.example.json \
  --output-dir data/company_scopes

PYTHONPATH=src python -m industry_first_research company-scope-validate \
  --input data/company_scopes/<scope>.json
```

行情进入市场结构、归因或模拟回放前，应先生成来源锁定快照：

```bash
PYTHONPATH=src python -m industry_first_research market-data \
  --input config/market_data_input.example.json \
  --market-registry config/market_registry.v1.json \
  --output-dir data/market_data

PYTHONPATH=src python -m industry_first_research market-structure \
  --input data/market_structure/<input>.json \
  --market-data data/market_data/<snapshot>.json
```

`market-data` 不自动下载行情，只接收已有的原始文件或标准化结果并锁定血缘；数据源仍按交易所/公司披露、东方财富、AKShare、BaoStock 的主备策略由上游采集器负责。连续序列只能用于结构研究，模拟决策和组合回放必须使用具体标的或具体期货合约。

生成或校验市场注册表：

```bash
PYTHONPATH=src python -m industry_first_research market-registry \
  --input config/market_registry.v1.json \
  --output-dir data/market_registries
```

## 开发

```bash
# Python 3.11 or newer is required; Python 3.12 is recommended.
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m pytest
python -m industry_first_research demo

# 可选免费数据依赖（Mac/Linux/Windows 均可）
python -m pip install -e '.[data]'
```

项目要求 Python 3.11 或更高版本；Python 3.9 不支持运行本项目。

启动本地 Web 研究控制台：

```bash
PYTHONPATH=src python -m industry_first_research web \
  --host 127.0.0.1 \
  --port 8765 \
  --data-root data
```

浏览器打开 `http://127.0.0.1:8765/`。控制台只展示已保存快照的元数据，并将输入统一交给本地
`resolve_research_task`；它不会替代研究管线，也不会改变交易、证据和人工发布边界。

统一解析用户输入（只分类，不联网、不调用模型、不启用执行）：

```bash
PYTHONPATH=src python -m industry_first_research resolve-task \
  --input-text "研究 600438.SH" \
  --as-of 2026-07-23 \
  --security-master data/security_master/<snapshot>.json \
  --commodity-config config/commodities/copper.json \
  --output-dir data/research_tasks

PYTHONPATH=src python -m industry_first_research validate-research-task \
  --input data/research_tasks/<task-id>.json
```

带 `.SH`、`.SZ`、`.BJ` 或 `.HK` 后缀的证券代码可完成语法级市场识别；提供本地轻量证券主数据后，
裸代码和公司名称可以进行精确匹配；提供 `--commodity-config` 后，配置内的期货中文别名和品种代码
可以分类为期货品种；没有主数据、多个候选或未提供交易所的期货品种会保留
`NEEDS_CONFIRMATION`，不会由解析器猜测身份。机会发现输入会归一为
`opportunity_scan`，所有输出的 `execution_enabled` 永远为 `false`。

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

机会发现可以显式复用 `luopan` / `ai-berkshire` 已导入的结构化候选集合：

```bash
PYTHONPATH=src python -m industry_first_research discover \
  --research-candidate-set data/research_assets/<candidate-set>.json \
  --max-selected-industries 3 \
  --company-pool-size 10
```

传入的文件必须是 `research-asset-candidate-set.v1`。候选集合是有边界的代表池，不是全市场主数据；
系统优先使用其中符合首期 A 股/港股范围的代码，非首期市场和重复项会记录为淘汰。没有合格候选时
才回退到既有公开公司池，非结构化研究报告不会被强行解析成公司成员。

`discover` 默认只读取每个行业源的前 50 条行业雷达记录；可用 `--radar-limit` 调整雷达上限。
它与每个入选行业的公司池大小 `--company-pool-size` 独立，仍然不会下载全市场个股深度数据。

`discover` 输出还包含派生的 `opportunity_discovery` 候选视图，保留下行保护、拐点证据、利润弹性、
未充分定价四维，行业/公司/市场三个时钟，硬闸门、缺口、候选状态和淘汰记录。LIGHT 资料缺失
保持为 `NOT_EVALUABLE`，不会被误判为失败。该层复用现有雷达、公司池和筛选结果，不加载全市场
公司深度数据，也不生成投资结论或模拟记录。

行业初筛已支持 `cycle_reversal`、`quality_repair`、`demand_acceleration` 和
`bottleneck_pricing` 四类机会。需求加速需要独立的需求/订单/商业化证据；瓶颈涨价需要稀缺、定价和
壁垒同时成立。单一价格、指数或概念标签不能升级状态，所有结果仍只是观察队列状态。

手工准备完整四维证据后，可单独评估候选或一轮有界扫描：

```bash
PYTHONPATH=src python -m industry_first_research opportunity-candidate \
  --input data/opportunity_candidate_inputs/<candidate>.json \
  --output-dir data/opportunity_candidates

PYTHONPATH=src python -m industry_first_research opportunity-scan \
  --input data/opportunity_candidate_inputs/<scan>.json \
  --output-dir data/opportunity_scans
```

`CANDIDATE` 要求生存/治理闸门通过、至少两类独立领先信号覆盖两个正常更新周期，且估值未明显透支；
`REVIEWABLE` 还要求产品盈利来源、生存压力测试、反向估值和对抗审查完成。空集、淘汰对象和重新
进入条件均保留，状态不是投资结论。

对公司池的 LIGHT 资料做只读完整度筛选：

```bash
PYTHONPATH=src python -m industry_first_research screen --input data/company_pools/tonghuashun-company-pool-881145-YYYY-MM-DD.json --expected-industry 电力 --alias-file docs/industry_aliases.v1.json
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

为 1-3 家公司生成完整深研字段模板时，可直接使用预设：

```bash
PYTHONPATH=src python -m industry_first_research evidence-template \
  --input data/candidate_queues/<queue>.json \
  --profile deep-company \
  --company-id 600519 \
  --company-id 000858 \
  --company-id 000568
```

`deep-company` 复用产品、应用、需求传导、行业处境、周期、竞争、生存、估值和反证模块
已有字段；模板仍为空白，不能直接作为已核验事实。

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

需求传导 `READY` 后，生成行业处境证据报告：

```bash
PYTHONPATH=src python -m industry_first_research industry-situation \
  --input data/company_demand_transmission/<demand-transmission>.json
```

该阶段整理长期需求、价值链利润分配、供需、库存、价格、开工、竞争、政策/技术/海外
因素、周期阶段、三个关键行业变量和反转验证条件。它不确认产业反转、不做生存分析、估值
或投资结论；这些模块必须等待后续阶段。

对适用的强周期或供需驱动行业，再生成产业供需与周期反转报告：

```bash
PYTHONPATH=src python -m industry_first_research cycle-reversal \
  --input data/company_industry_situations/<industry-situation>.json
```

该阶段区分 `PRICE_REBOUND`、`TURNING_POINT_CANDIDATE` 和
`INDUSTRIAL_REVERSAL_CONFIRMED`，并要求相应的需求、有效供给、库存、价格、供给退出和
行业现金流证据。非适用行业明确标记 `NOT_APPLICABLE`；该报告不做生存、估值或投资结论。

周期证据通过后，建立公司商业模式与竞争位置报告：

```bash
PYTHONPATH=src python -m industry_first_research competitive-position \
  --input data/company_cycle_reversals/<cycle-reversal>.json
```

该阶段覆盖商业模式、收入结构、成本、技术、客户、渠道、资本、市场份额和竞争矩阵
（成本、性能、良率、认证、交付、客户、规模、替代路线）。证据不完整时只输出缺口，
不会把核心部件、高增长或单一竞争维度自动升级为护城河，也不做生存、估值或投资结论。

竞争位置证据通过后，运行生存能力与极端压力测试闸门：

```bash
PYTHONPATH=src python -m industry_first_research survival-analysis \
  --input data/company_competitive_positions/<competitive-position>.json
```

该步骤要求六个压力情景：低谷延长、再融资失败、经营冲击、资产减值、技术替代和治理冲击；
每个情景必须保留现金跑道、债务缺口、最低现金余额、资本开支可削减程度、资产出售动作、
融资依赖度和生存结果。`self_funded`、`refinancing_dependent`、`external_support_dependent`
分开记录，证据不足时不输出生存者或反转受益者结论。

生存闸门通过后，建立三情景估值框架和反向估值检查：

```bash
PYTHONPATH=src python -m industry_first_research valuation-scenarios \
  --input data/company_survival_analysis/<survival-analysis>.json
```

该步骤要求悲观、基准、乐观三种情景，以及当前价格时点、历史财务、周期中枢利润、净债务
和稀释、反向估值假设、证据支持假设、模型假设、基准情景排除项和敏感性。当前只生成
可审计的估值框架，不计算目标价，不生成投资结论，也不把未验证风口或周期高点利润放进基准情景。

估值框架之后可选生成市场结构辅助快照。输入必须先锁定标的、数据截止时间、周期、复权和
OHLCV 快照：

```bash
PYTHONPATH=src python -m industry_first_research market-structure \
  --input data/market_structure/<input>.json
```

该步骤只输出多周期趋势、波动、区间位置、确认状态和重绘风险，不输出买卖信号或自动交易；
期货连续序列还必须保留主力、换月、拼接和复权规则。

并列检查本地结构、`czsc` 和 `chan.py`（外部包为可选依赖）：

```bash
PYTHONPATH=src python -m industry_first_research market-structure-compare \
  --input data/market_structure/<input>.json \
  --output-dir data/market_structure_comparisons
```

结果分别保存每个实现的版本、状态、结构字段和原始输出哈希。未安装或未配置 runner 的外部
实现会记录 `PACKAGE_NOT_INSTALLED` 或 `RUNNER_NOT_CONFIGURED`，不影响本地结构结果；实现之间
出现差异时标记 `DIVERGENT` 并降低置信度，不拼接为共识信号，也不输出自动买卖建议。

估值和市场结构资料完成后，运行对抗审查：

```bash
PYTHONPATH=src python -m industry_first_research adversarial-review \
  --input data/company_valuation_scenarios/<valuation-scenarios>.json \
  --market-structure data/market_structure/<snapshot>.json
```

审查主动检查未来信息、冲突证据、反证和失效条件、利润到现金流转换、基准排除项、网页
AI 独立性、市场规模到公司利润的错误跳推、估值输出边界、市场结构信号泄漏和候选状态变更。
结果为 `PASS`、`REVIEW` 或 `BLOCKED`，只记录问题，不改写事实或生成投资结论。

对抗审查完成后，生成结构化公司研究报告和后续跟踪清单：

```bash
PYTHONPATH=src python -m industry_first_research research-report \
  --input data/company_adversarial_reviews/<adversarial-review>.json
```

报告分开整理行业处境、公司质量、产品与需求传导、生存压力、估值框架、风险反证和跟踪
清单。只有审查 `PASS` 且候选状态允许时标记 `REVIEWABLE`；该步骤不生成方向性投资结论、
目标价或模拟决策快照，模拟记录必须等待用户确认。

从已锁定研究报告生成微信公众号公开草稿（当前仅本地脱敏和人工审核前检查）：

```bash
PYTHONPATH=src python -m industry_first_research public-draft \
  --input data/company_research_reports/<locked-report>.json \
  --source-lock data/research_versions/<lock>.json \
  --output-dir data/public_drafts

PYTHONPATH=src python -m industry_first_research validate-public-draft \
  --input data/public_drafts/<public-draft-id>.json
```

来源锁定对象必须是 `LOCKED` 或 `USER_CONFIRMED`，且哈希必须与报告完全匹配。生成器会递归删除目标价、预期收益、仓位、模拟成交、账户、订单、券商和私人备注等字段，并记录删除路径；敏感表达会将草稿置为 `BLOCKED`，未命中也只得到 `NEEDS_HUMAN_REVIEW`。来源公开性、版权、图片/表格授权和时效仍需人工复核，任何本地结果固定为 `NOT_PUBLISHED`，不会调用公众号接口或修改原报告。

把一份补充证据包串成完整有限公司深研链路：

```bash
PYTHONPATH=src python -m industry_first_research research-pipeline \
  --input data/company_supplemental/<supplemental>.json \
  --evidence-bundle data/evidence/<bundle>.json
```

统一证据包作为管线的事实与时间截面审计引用，输出其 ID、证据清单哈希、截止日状态和
未来证据复核状态；现有阶段仍只消费已经明确填写的字段，不会把证据包中的自由文本自动
当成事实。该命令不自动补事实、不升级 `WATCH`、不生成投资结论；每个阶段的完整快照
保存在输出中的 `stages`，最终状态在 `final_state`。

检查能力复用矩阵：

```bash
PYTHONPATH=src python -m industry_first_research capability-matrix \
  --input config/capabilities/initial-matrix.json \
  --output-dir data/capabilities
```

矩阵会保留组件接口、输出质量、许可证、截止日能力、安全边界和最终判定。`NEW_DEVELOPMENT`
必须填写 `capability_gap`；如果只是字段或协议不一致，应优先记录为 `ADAPTER_REUSE`。

回放机会发现过程质量：

```bash
PYTHONPATH=src python -m industry_first_research opportunity-quality \
  --input data/opportunity_quality/<quality-input>.json \
  --output-dir data/opportunity_quality
```

输入保留多次 `opportunity-scan.v1` 快照，可附带硬否决、误报和漏报人工抽样标签。报告
计算扫描覆盖、观察到候选的比例、候选进入深研/可复核的比例、状态迁移、状态停留时间和
空集频率；没有人工复核标签时保持 `NOT_EVALUABLE`，不会用上涨、收益或事后价格重写历史状态。

对已有研究做增量更新：

```bash
PYTHONPATH=src python -m industry_first_research incremental-update \
  --previous-pipeline data/company_research_pipelines/<pipeline>.json \
  --previous-supplemental data/company_supplemental/<supplemental>.json \
  --evidence data/supplemental_evidence/<new-records>.json \
  --as-of 2026-07-21
```

该命令保留旧版本，检查证据 ID 是否被篡改，识别新增/变化/冲突字段并映射受影响模块。
当前阶段会先生成增量影响计划，再完整重跑有限公司研究链路；不会静默覆盖旧结论、自动改变
方向性判断或创建模拟决策。

初始化本地持续跟踪调度状态：

```bash
PYTHONPATH=src python -m industry_first_research schedule-init \
  --output-dir data/scheduler
```

生成一轮到期任务计划，并可导入人工或采集器产生的事件：

```bash
PYTHONPATH=src python -m industry_first_research schedule-plan \
  --schedule data/scheduler/schedule-default.json \
  --state data/scheduler/state-default.json \
  --events data/scheduler/events.json \
  --now 2026-07-21T09:00:00+08:00
```

调度器只负责计划、去重、范围约束、重试和降级留痕；不下载全市场深度数据、不调用
网页 AI、不改变研究方向结论，也不创建模拟决策。`schedule-run` 通过现有数据适配器执行
受限任务，本地计划可以由 macOS `launchd`、cron 或其他定时器周期调用。

执行已生成的本地任务计划：

```bash
PYTHONPATH=src python -m industry_first_research schedule-run \
  --state data/scheduler/state-default.json \
  --plan data/scheduler/<scheduler-plan>.json \
  --output-root data
```

也可以手工比较两个已保存的期货基本面报告：

```bash
PYTHONPATH=src python -m industry_first_research futures-tracking \
  --current data/futures_fundamentals/<current-report>.json \
  --previous data/futures_fundamentals/<previous-report>.json \
  --as-of 2026-07-21 \
  --output-dir data/futures_tracking
```

`futures-tracking` 只读取本地 `futures-fundamentals-report.v1`，比较状态、现货/库存/仓单、成本、
基差、期限结构和情景字段，保留前后报告不变。默认 `schedule-init` 生成的
`futures_fundamentals_delta_scan` 任务也只读取有界的 `data/futures_fundamentals` 目录，不自动下载全市场数据、
不选择方向、不创建模拟决策。

研究管线与调度器会自动生成研究版本清单。也可以手工从已有管线生成、校验、比较和准备回放：

```bash
PYTHONPATH=src python -m industry_first_research research-version \
  --input data/company_research_pipelines/<pipeline>.json \
  --supplemental data/company_supplemental/<supplemental>.json \
  --output-dir data/research_versions

PYTHONPATH=src python -m industry_first_research validate-research-version \
  --input data/research_versions/<version>.json

PYTHONPATH=src python -m industry_first_research compare-research-versions \
  --previous data/research_versions/<old-version>.json \
  --current data/research_versions/<new-version>.json

PYTHONPATH=src python -m industry_first_research replay-research-version \
  --version data/research_versions/<version>.json \
  --artifacts data/replay_inputs/<artifacts>.json
```

版本清单只保存引用和哈希，不复制研究正文。历史管线、证据、行情和决策对象只写一次；调度器
的 state、临时计划可以覆盖，按日期或事件 ID 的研究产物和版本清单不可覆盖。回放不会联网、不会
调用模型、不会生成方向性结论，也不会修改历史对象。

检查数据源适配器状态并保存不可变快照：

```bash
PYTHONPATH=src python -m industry_first_research source-health \
  --output-dir data/source_health

PYTHONPATH=src python -m industry_first_research validate-source-health \
  --input data/source_health/<source-health-snapshot>.json
```

可以用 `--source`、`--subject-type` 和重复的 `--required-capability subject_type=capability`
缩小检查范围。健康快照只表示适配器和依赖的就绪状态，不表示远端接口可达、返回结果非空或
字段完整；真实研究仍必须执行 `DataSourceRouter.fetch`，并保存每个来源的尝试、失败原因和最终来源。
快照写入 `data/source_health` 后不可覆盖，重复检查应使用新的快照 ID。

按显式查询清单执行一次有界数据刷新：

```bash
PYTHONPATH=src python -m industry_first_research data-refresh \
  --input config/data_source_refresh_input.example.json \
  --output-dir data/data_source_refreshes

PYTHONPATH=src python -m industry_first_research validate-data-refresh \
  --input data/data_source_refreshes/<refresh-id>.json
```

刷新清单必须逐条声明研究对象、查询请求和可用来源顺序；默认最多 20 条查询、每条最多保留 500 行。
路由会在来源健康检查、请求失败、空结果或字段不全时切换下一个来源，并保留所有 `DataSourceAttempt`。
刷新结果只是不可变原始采集快照，不自动进入正式证据或研究结论；`SUCCESS`、`PARTIAL` 和
`INSUFFICIENT` 分别表示全成功、有界截断/部分成功和没有有效结果。清单为空时明确记录未配置，
不会联网、不猜测研究对象、不下载全市场个股深度数据。

数据源协议的本地回归使用 `tests/fixtures/data_sources/` 中的交易所/公司披露、东方财富、AKShare
和 BaoStock 固定响应，不访问网络。夹具只验证主备路由、失败尝试、返回哈希和刷新校验可重建，不代表
远端接口当前可用，也不会把夹具内容升级为正式证据。

刷新结果进入正式证据前，使用人工字段映射闸门：

```bash
PYTHONPATH=src python -m industry_first_research evidence-from-refresh \
  --refresh data/data_source_refreshes/<refresh-id>.json \
  --records data/refresh_evidence_inputs/<records>.json \
  --output-dir data/refresh_evidence_gates

PYTHONPATH=src python -m industry_first_research validate-evidence-from-refresh \
  --input data/refresh_evidence_gates/<gate-id>.json
```

默认只生成 `REVIEW_REQUIRED` 的候选记录；只有增加 `--user-confirmed`、审核人、时间和理由，才会
生成 `evidence-bundle.v1`。刷新快照、来源文档哈希和旧研究版本不变，证据提升不会生成买卖结论。

生成或比较两次刷新快照的变化清单：

```bash
PYTHONPATH=src python -m industry_first_research data-refresh-track \
  --current data/data_source_refreshes/<current-refresh>.json \
  --previous data/data_source_refreshes/<previous-refresh>.json \
  --output-dir data/data_source_refresh_tracking

PYTHONPATH=src python -m industry_first_research validate-data-refresh-track \
  --input data/data_source_refresh_tracking/<tracking-id>.json
```

跟踪结果会输出 `INITIALIZED`、`UPDATED`、`NO_CHANGE` 或 `PARTIAL`，列出变化的查询、来源、数据哈希、
截断和尝试状态；它只生成待复核差异，不升级证据、研究结论或模拟决策。

执行器复用现有行业雷达和公司池适配器；每日增量只生成行业趋势与候选容量摘要，事件任务默认
只生成受影响模块的待复核记录。若事件 payload 同时明确提供本地旧管线、旧补充证据和新增证据
文件路径，事件任务会复用 `incremental-update` 生成新的补充证据、公司管线和研究版本；缺少任一
输入时不会猜测或抓取全量数据。公司池刷新只加载 10-30 家 LIGHT 数据，不自动进入深研。

自动增量事件的本地输入约定如下：

```json
{
  "payload": {
    "previous_pipeline_path": "data/company_research_pipelines/<old>.json",
    "previous_supplemental_path": "data/company_supplemental/<old>.json",
    "evidence_path": "data/supplemental_evidence/<new-records>.json",
    "execution_mode": "LOCAL_ONLY"
  }
}
```

成功后旧对象保留不变，新对象写入 `company_supplemental`、`company_research_pipelines`、
`company_incremental_updates` 和 `research_versions`；新版本仅表示事实和受影响模块已刷新，
语义结论、持有论文和模拟决策仍需复核/用户确认。

每日增量同时写入 `opportunity_tracking`：对比最近两次候选快照的状态和四维变化，关联行业趋势、
候选队列变化及受影响模块。趋势或队列变化只有在缺少新的四维候选证据时会生成复核项，不会自动
升级/降级候选；没有候选快照时明确记录 `NO_SNAPSHOT`。

检查证据新鲜度：

```bash
PYTHONPATH=src python -m industry_first_research freshness \
  --input data/company_supplemental/<supplemental>.json \
  --as-of 2026-07-21
```

比较两次研究版本：

```bash
PYTHONPATH=src python -m industry_first_research compare-versions \
  --previous-pipeline data/company_research_pipelines/<old-pipeline>.json \
  --current-pipeline data/company_research_pipelines/<new-pipeline>.json \
  --previous-supplemental data/company_supplemental/<old-supplemental>.json \
  --current-supplemental data/company_supplemental/<new-supplemental>.json
```

检查用户已锁定的持有论文：

```bash
PYTHONPATH=src python -m industry_first_research thesis-check \
  --thesis data/holding_theses/<thesis>.json \
  --supplemental data/company_supplemental/<supplemental>.json \
  --as-of 2026-07-21
```

这些命令只生成新鲜度、版本差异和建议论文状态；旧版本不覆盖，论文状态需要用户或后续
语义复核确认后另建版本，价格下跌本身不会自动判定论文破裂。

创建论文草稿或在用户确认后锁定论文版本：

```bash
PYTHONPATH=src python -m industry_first_research thesis-lock \
  --input data/holding_theses/<thesis-input>.json \
  --user-confirmed \
  --output-dir data/holding_theses
```

修订已锁定论文时必须提供 `--previous-thesis`、递增 `version`、`supersedes_thesis_id`
和 `revision_reason`；原论文不会被覆盖。

用户确认后，才可从 `REVIEWABLE` 研究报告创建不可覆盖的模拟决策快照：

```bash
PYTHONPATH=src python -m industry_first_research decision-snapshot \
  --input data/company_research_reports/<research-report>.json \
  --decision data/decision_inputs/<decision>.json \
  --evidence-bundle data/evidence/<bundle>.json \
  --execution-plan data/research_execution/<plan>.json \
  --company-scope data/company_scopes/<scope>.json \
  --market-data data/market_data/<asset-snapshot>.json \
  --user-confirmed
```

快照保存研究对象、决策时间、数据截面、模拟动作、方向、价格/数量/资金假设、理由、风险、
触发/失效条件、复查日期和基准，并固定为 `LOCKED`。如提供统一证据包和执行计划，还会
锁定证据清单哈希、研究深度、执行模式和计划 ID；提供公司边界或行情快照时，还会锁定
公司边界 ID/内容哈希、行情快照 ID/内容哈希。证据包、执行计划、公司边界或行情快照晚于
决策截止日时直接拒绝。期货快照必须绑定具体合约，不能绑定连续序列；修改只能创建新版本，
不连接券商、不发送委托。

达到快照中锁定的复查日期后，使用同一份锁定快照生成只读复盘与归因：

```bash
PYTHONPATH=src python -m industry_first_research attribution \
  --input data/decision_snapshots/<decision-snapshot>.json \
  --outcome data/attribution_inputs/<outcome>.json \
  --closed-at 2026-08-19
```

公司结果要求标的与快照锁定的基准使用相同日期序列，并拆分价格、分红、汇率和成本；
期货结果要求具体合约的逐日结算账本，并单列盯市、保证金、手续费、滑点、移仓和模拟强平。
基准不允许在复盘时替换，未到复查日期或数据不可比时输出 `NOT_EVALUABLE`。解释性归因默认
为 `ROUGH_ATTRIBUTION`，不会把相关性写成因果或生成交易结论。

对已完成的模拟复盘生成研究质量评分卡：

```bash
PYTHONPATH=src python -m industry_first_research quality-scorecard \
  --input data/decision_snapshots/<decision-snapshot>.json \
  --attribution data/attribution_results/<attribution>.json \
  --research-report data/company_research_reports/<research-report>.json \
  --output-dir data/quality_scorecards
```

评分卡分别复核事实准确性、状态判断、模型假设、风险识别、估值质量、决策过程和结果表现，
并保留机会发现的空结果、淘汰和选择偏差指标。它不生成综合总分，不用收益率证明事实正确，
后验材料不足时输出 `NOT_EVALUABLE`；只读评分卡不会修改决策快照、研究结论或执行任何交易。

把多次用户确认的公司模拟操作组成一个全额资金模拟组合：

```bash
PYTHONPATH=src python -m industry_first_research portfolio-create \
  --input data/simulation_portfolio_inputs/<portfolio-input>.json \
  --decision data/decision_snapshots/<open>.json \
  --decision data/decision_snapshots/<adjust-or-hold>.json \
  --decision data/decision_snapshots/<exit>.json \
  --output-dir data/simulation_portfolios
```

组合只引用 `LOCKED` 的公司决策快照；`ADJUST` 的数量是调整后的目标数量，`HOLD` 保持原数量，
原始快照和理由不会被组合层覆盖。使用带日期的行情与基准数据回放组合效果：

```bash
PYTHONPATH=src python -m industry_first_research portfolio-replay \
  --input data/simulation_portfolios/<simulation-portfolio>.json \
  --outcome data/simulation_portfolio_inputs/<dated-outcome>.json \
  --closed-at YYYY-MM-DD \
  --output-dir data/simulation_portfolio_replays
```

回放输出每日现金、持仓市值、组合权益、分红、费用、最大回撤、组合收益、锁定基准收益和超额收益。
缺少操作日数据、出现复查日后的数据或现金假设不足时不会补算，结果标为 `NOT_EVALUABLE` 或
 `REVIEW_REQUIRED`。该组合账本仅覆盖上市公司全额资金口径；国内期货继续使用具体合约的逐日盯市账本，
 不与股票保证金/全额资金收益混合。

国内商品期货使用独立的具体合约结算账本。先用已确认的期货决策快照创建模拟记录：

```bash
PYTHONPATH=src python -m industry_first_research futures-simulation-create \
  --input config/futures_simulation_input.example.json \
  --decision data/decision_snapshots/<futures-open>.json \
  --decision data/decision_snapshots/<futures-hold-or-roll>.json \
  --decision data/decision_snapshots/<futures-exit>.json \
  --output-dir data/futures_simulations
```

使用交易所结算价、当日适用保证金率、规则版本、涨跌停可成交状态和锁定基准进行回放：

```bash
PYTHONPATH=src python -m industry_first_research futures-simulation-replay \
  --input data/futures_simulations/<futures-simulation>.json \
  --outcome config/futures_simulation_outcome.example.json \
  --closed-at YYYY-MM-DD \
  --output-dir data/futures_simulation_replays
```

输出逐日盯市盈亏、现金余额、保证金占用、可用模拟资金、手续费、滑点、显式移仓诊断、追加资金、
保证金调用、涨跌停阻断和模拟强平状态。移仓必须在决策快照中明确两条合约和两条成交价；系统不自动
换月、不自动追加真实资金、不发送委托。连续序列、主力代码和缺少规则版本的结算行不能作为模拟输入。

回放结果可以直接作为共享归因命令的结果输入，归因层会保留期货保证金口径，不把它与股票全额资金收益相减：

```bash
PYTHONPATH=src python -m industry_first_research attribution \
  --input data/decision_snapshots/<futures-open>.json \
  --outcome data/futures_simulation_replays/<futures-replay>.json \
  --closed-at YYYY-MM-DD \
  --output-dir data/attribution_results
```

识别国内商品期货研究对象：

```bash
PYTHONPATH=src python -m industry_first_research futures-identify \
  --input data/futures_inputs/<variety-contract-or-series>.json \
  --output-dir data/futures_identities
```

对象明确区分商品品种、具体月份合约、连续研究序列和现货基准。连续序列必须保存主力判定、
换月、拼接、复权和真实合约组件规则，但 `simulation_allowed=false`；只有交易所、合约代码、
月份、最后交易日、乘数、最小变动、结算口径和规则版本齐全的具体合约才可进入模拟决策。

在身份确认后，使用交易所、东方财富、AKShare 或人工核验后的有界证据包生成 F1-F10 期货研究底座：

```bash
PYTHONPATH=src python -m industry_first_research futures-fundamentals \
  --identity data/futures_identities/<identity>.json \
  --input data/futures_inputs/<fundamentals>.json \
  --output-dir data/futures_fundamentals
```

输入使用 `futures-fundamentals-input.v1`，研究截面由 `as_of` 固定，字段可附带
`evidence_ids`、来源、单位和字段状态。报告分别保存 `variety_view`、`contract_view`、
`market_structure` 和 `simulation_view`：它会计算已提供且单位明确的现货/合约差、基差、成本差、
库存与仓单变化，但不会补齐缺失数据、计算“内在价值”、选主力合约或创建决策快照。缺少现货、
库存/仓单、基差、期限结构或交割规则时，报告会降级为 `PARTIAL` / `INSUFFICIENT`，并列出补证清单。
价格情景只是悲观、基准、乐观观察区间；只有具体月份合约且用户后续确认，才可能进入现有模拟决策流程。

将已经完成主备路由的数据刷新结果映射为期货基本面输入：

```bash
PYTHONPATH=src python -m industry_first_research futures-input-from-refresh \
  --refresh data/data_source_refreshes/<refresh>.json \
  --mapping config/futures_fundamentals_refresh_mapping.example.json \
  --output-dir data/futures_inputs
```

映射文件中的 `value_path`、`rows_path` 和 `date_path` 都指向来源适配器标准化后的结果，
不会执行模糊匹配。查询对象必须与映射中的 `variety_id` 一致；失败或其他品种的刷新结果会被拒绝。
该命令只生成待复核输入，不把原始刷新直接升级为事实、不生成方向结论，也不创建模拟决策。

将已确认的期货品种与上市公司产品暴露连接时，必须提供公司产品、明确角色和证据：

```bash
PYTHONPATH=src python -m industry_first_research futures-company-exposure \
  --futures-report data/futures_fundamentals/<report>.json \
  --input data/futures_company_exposures/<input>.json \
  --output-dir data/futures_company_exposures
```

输入使用 `futures-company-exposure-input.v1`。暴露角色区分 `PRODUCER`、`CONSUMER`、
`PROCESSOR`、`TRADER` 和 `BILATERAL`，并记录收入/成本链接、定价滞后、库存影响、套保政策、
传导假设和来源证据。也可以通过 `--product-profile` 复用已有 `company-product-profile.v1`。
行业标签不能代替产品证据；只有产品精确匹配且产品证据已验证时，才输出条件式方向和情景桥接，
数字结果始终是显式假设下的说明性影响，不是公司利润预测、目标价或投资结论。

商品品种适配器采用配置驱动方式维护，不需要为每个新商品复制一套研究核心：

```bash
PYTHONPATH=src python3 -m industry_first_research commodity-adapters \
  --directory config/commodities \
  --output-dir data/commodity_adapters
```

适配器配置定义品种代码、交易所、现货基准、供需指标、库存/仓单环节、成本与产业利润、季节性、
交割规则、情景方法和验收样例。对具体期货报告和基本面输入执行兼容性检查：

```bash
PYTHONPATH=src python3 -m industry_first_research commodity-adapter-validate \
  --directory config/commodities \
  --adapter CU \
  --futures-report data/futures_fundamentals/<report>.json \
  --fundamentals data/futures_inputs/<fundamentals>.json \
  --output-dir data/commodity_adapter_validations
```

当前提供钢材、原油、豆粕、铜、碳酸锂和天然橡胶 6 类配置，覆盖 `RB`、`HC`、`SC`、`M`、`CU`、`BC`、`LC`、`RU`。
适配器只定义研究问题和数据契约，不抓取数据、不选择方向；品种、交易所、现货基准或指标口径不匹配时输出
`PARTIAL` / `BLOCKED`，不会静默套用其他商品的模型。配置目录通过回归测试后，仍需对每个品种分别完成交易所/现货数据和时间截面验证。

保存不可变原始公告资产和版本链：

```bash
PYTHONPATH=src python -m industry_first_research announcement-asset \
  --input data/announcement_inputs/<announcement>.json \
  --raw-content data/announcement_inputs/<original-file> \
  --output-dir data/announcement_assets
```

公告原件复制到 `raw/`，清单保留主体、公告类型、来源、发布时间、抓取时间、解析器版本、内容哈希、
版本和更正/补充/撤回关系。生成受影响模块的待复核记录：

先对用户手工提供的公告原文做本地解析。该步骤不访问 URL；URL 只作为来源血缘和后续人工核验地址：

```bash
PYTHONPATH=src python -m industry_first_research announcement-templates \
  --config config/announcement_templates.v1.json \
  --output-dir data/announcement_templates

PYTHONPATH=src python -m industry_first_research announcement-parse \
  --input data/announcement_inputs/<original-file> \
  --template official_exchange \
  --source-url https://example.com/original-disclosure \
  --subject-type listed_company \
  --subject-id 600438 \
  --output-dir data/announcement_inputs
```

解析输出为 `original-announcement-input.v1`。`READY` 或 `DEGRADED` 输入可继续进入
`announcement-asset`；`BLOCKED` 只保存失败原因和来源尝试链，必须补齐主体、发布时间、标题或更正父文档后再提升。
模板只描述 URL/参数契约、文档类型映射和字段定位，不代表事实；东方财富等聚合来源仍需回溯交易所或公司原始披露。

产品桥接可独立运行：

```bash
PYTHONPATH=src python -m industry_first_research product-profit-bridge \
  --input data/product_profit_bridge_inputs/<bridge>.json \
  --output-dir data/product_profit_bridges

PYTHONPATH=src python -m industry_first_research product-profit-bridge-validate \
  --input data/product_profit_bridges/<bridge-report>.json
```

它只输出产品经济学参考结果，不输出目标价、买卖结论或交易指令。

产品生命周期快照可独立运行：

```bash
PYTHONPATH=src python -m industry_first_research product-lifecycle \
  --input config/product_lifecycle_input.example.json \
  --output-dir data/product_lifecycles

PYTHONPATH=src python -m industry_first_research product-lifecycle-validate \
  --input data/product_lifecycles/<snapshot>.json
```

财务模型可独立运行：

```bash
PYTHONPATH=src python -m industry_first_research financial-model \
  --input config/financial_model_input.example.json \
  --output-dir data/financial_models

PYTHONPATH=src python -m industry_first_research financial-model-validate \
  --input data/financial_models/<model>.json
```

该模型只输出可复算的参考数字和数据缺口，不输出目标价、买卖结论或交易指令。

```bash
PYTHONPATH=src python -m industry_first_research announcement-impact \
  --input data/announcement_assets/<document>-v<version>.json \
  --research-cutoff YYYY-MM-DDTHH:MM:SS+08:00 \
  --output-dir data/announcement_impacts
```

公告资产和影响记录只更新证据时间线与待复核模块，不覆盖历史研究、持有论文或决策快照；截止日之后
发布的更正不会回填到截止日以前的研究。

把公告影响关联到已经保存的研究版本：

```bash
PYTHONPATH=src python -m industry_first_research research-impact-queue \
  --event data/announcement_impacts/<impact>.json \
  --versions-dir data/research_versions \
  --output-dir data/research_impact_queues

PYTHONPATH=src python -m industry_first_research validate-research-impact-queue \
  --input data/research_impact_queues/<queue>.json
```

队列按研究对象和时间截面匹配版本。事件早于某版本截止日时标记为需要修订，事件晚于截止日时
只能创建后续版本，不能回填旧版本；没有匹配版本也会保留 `NO_MATCHING_VERSION` 记录。

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

# 白酒行业纵向切片
PYTHONPATH=src python -m industry_first_research industry \
  --config config/industries/baijiu.json \
  --output /tmp/baijiu-report.md \
  --html-output /tmp/baijiu-report.html

# 可离线复跑的白酒黄金链路（合成夹具，不是投资证据）
PYTHONPATH=src python -m industry_first_research industry \
  --config tests/fixtures/baijiu/config.json \
  --snapshot-dir /tmp/baijiu-golden-snapshots \
  --output /tmp/baijiu-golden-report.md \
  --html-output /tmp/baijiu-golden-report.html

# 通威股份公司快照（按交易所/公司披露、东方财富、AKShare、BaoStock 主备切换）
PYTHONPATH=src python -m industry_first_research company \
  --config config/companies/600438.json

# 只采集配置中的行业信号，不加载公司池或全市场深度数据
PYTHONPATH=src python -m industry_first_research industry-radar \
  --config config/industries/your-industry.json
```

生产白酒配置引用的本地研究文件未检入时，来源完整性会降级为
`INSUFFICIENT`，相关公司因没有可用配置资产而进入 `BLOCKED`，不会继续进入深研层。
黄金链路只用于验证 13 家轻量公司、5 家深度公司和确定性输出；同内容重复执行是幂等的，
不同内容复用同一不可变路径会报冲突。

## 外部研究资产

本地 `vendor/luopan` 和 `vendor/ai-berkshire` 是用于开发和研究验证的上游工作树。由于本仓库是公开仓库，当前不自动提交其中的历史报告、数据和完整工作树；来源版本记录在 [`vendor/SOURCES.md`](vendor/SOURCES.md)。后续会通过适配器引用或按许可证明确允许的内容接入。

当前已提供只读研究资产适配器。它会保留原始文件路径、SHA-256、文件修改时间、研究日期、上游提交版本和映射版本；研究截止日之后的资产会进入排除清单，不会回填历史研究：

```bash
# 发现两个上游仓库中与公司/行业标识匹配的资产
PYTHONPATH=src python -m industry_first_research research-assets \
  --mode discover \
  --root . \
  --identifier NVIDIA \
  --as-of 2026-07-21 \
  --output-dir data/research_assets

# 将明确的公司身份、市场和主营/产品候选映射出来
PYTHONPATH=src python -m industry_first_research research-assets \
  --mode profile \
  --root . \
  --input vendor/luopan/review-output/NVIDIA-公司调研-2026-07-12.json \
  --output-dir data/research_assets

# 导入有边界的 watchlist 候选集
PYTHONPATH=src python -m industry_first_research research-assets \
  --mode candidate-set \
  --root . \
  --input vendor/ai-berkshire/data/watchlist.json \
  --output-dir data/research_assets
```

身份、行业、主营和产品均先作为候选字段；与交易所/公司正式披露一致性校验后才可进入事实层。`luopan` 公司池始终标记为代表性候选集合，不能冒充证券主数据。估值、目标价、买卖观点和外部报告结论统一为 `REFERENCE_ONLY`；外部报告重复出现同一观点也不会自动提高证据等级。该适配器不修改上游文件、不复制报告全文、不联网、不生成投资结论或交易指令。

构建轻量证券主数据和带生效时间的行业成员历史：

```bash
# 可使用显式 security-master-input.v1，或直接转换已有 bounded company-pool 快照
PYTHONPATH=src python -m industry_first_research security-master \
  --input data/company_pools/tonghuashun-company-pool-881273-2026-07-20.json \
  --output-dir data/security_master

# 后续日期更新时传入上一版快照；行业变更会关闭旧关系并打开新关系
PYTHONPATH=src python -m industry_first_research security-master \
  --input data/security_master/<new-input>.json \
  --previous data/security_master/<previous-snapshot>.json \
  --output-dir data/security_master

PYTHONPATH=src python -m industry_first_research security-master-validate \
  --input data/security_master/<snapshot>.json
```

主数据只保存公司代码、名称、市场、上市/停牌/退市状态、行业归属和来源血缘；不保存全市场日线、财务、估值、技术指标或公告全文。行业成员关系使用半开区间 `[effective_from, effective_to)`：有完整市场覆盖时，缺席可以关闭旧关系；只有 bounded 行业池时，缺席不代表退出。市场字段缺失不会根据股票代码猜测，研究候选集也不会写入证券主数据。

行业分类和行业分析问题采用配置驱动适配器：

```bash
PYTHONPATH=src python -m industry_first_research industry-adapters \
  --directory config/industries/adapters \
  --output-dir data/industry_adapters

PYTHONPATH=src python -m industry_first_research industry-profile \
  --input data/industry_profile_inputs/<profile>.json \
  --directory config/industries/adapters \
  --output-dir data/industry_profiles
```

当前配置包含通用公司、周期制造和消费品牌三个适配器。适配器负责选择行业指标、估值方法、低谷生存问题、产品—应用问题和需求传导阶段；未知行业降级到 `generic_company`，非周期行业不生成周期模型。分类结果是候选分类，不是已核验事实；产品暴露必须有明确产品和证据，适配器不抓数据、不从概念标签推导受益、不输出投资结论。

## 统一证据与数据血缘

统一证据层把原始公告、交易所/公司披露、东方财富、AKShare、BaoStock、行业资料和人工粘贴的网页 AI 线索转换成可追溯对象。它只保存研究事实、假设和中间产物，不生成投资结论或交易指令：

```bash
# 先把原始文件或响应保存成不可变来源文档清单
PYTHONPATH=src python -m industry_first_research source-document \
  --input data/source_inputs/<document>.json \
  --raw-content data/source_inputs/<original-file> \
  --output-dir data/source_documents

# 构建统一证据包，并按 subject_id/metric/period/unit 记录冲突裁决
PYTHONPATH=src python -m industry_first_research evidence \
  --input data/evidence_inputs/<input>.json \
  --output-dir data/evidence \
  --reconcile
```

输入可包含 `source_documents`、`evidence`、`model_assumptions`、`research_artifacts`、
`research_candidate_sets` 和 `scorecard_artifacts`。每条证据必须保留来源文档、发布时间、
抓取时间、研究截止日、内容哈希、页码/段落/表格/字段路径、证据等级、核验状态和字段级
`field_lineage`。截止日之后的证据进入 `excluded_future_evidence_ids`，不会回填旧报告；
历史修订使用新文档或证据 ID 与 `supersedes_*` 链，不能覆盖旧对象。

证据状态使用 `verified_fact`、`cross_validated`、`company_claim`、`market_signal`、
`model_assumption` 和 `unknown`。网页 AI 只能使用 `C_external_ai_lead` 或
`D_unverified_model_claim`，没有显式人工复核记录时不能升级为正式事实。多个来源出现不同
值时，系统保留每个原始值；只有明确来源优先级或人工裁决才采用一个值，无法裁决则为
`CONFLICTING`，不做静默平均。

`SourceDocument` 与现有不可变公告资产互补：公告资产继续维护公告更正/补充/撤回链，统一
证据层提供跨公告、行情、行业序列和外部研究资产的公共证据接口。`luopan` 和
`ai-berkshire` 的画像、候选集和评分卡仍是可复用研究资产，不会绕过统一证据层直接成为事实。

研究深度和是否调用模型是两个独立维度：

```bash
# 归一化一次研究请求
PYTHONPATH=src python -m industry_first_research research-request \
  --input data/research_inputs/<request>.json \
  --output-dir data/research_execution

# 生成本地/模型执行计划；默认不调用模型
PYTHONPATH=src python -m industry_first_research research-plan \
  --input data/research_execution/<request>.json \
  --output-dir data/research_execution

# 记录已授权模型调用的审计信息，不由该命令发起调用
PYTHONPATH=src python -m industry_first_research llm-run \
  --input data/research_execution/<llm-run>.json \
  --output-dir data/research_execution

# 将模型调用与计划对照，发现未计划模块或预算超限时阻断审计
PYTHONPATH=src python -m industry_first_research execution-audit \
  --plan data/research_execution/<plan>.json \
  --runs data/research_execution/<runs>.json \
  --output-dir data/research_execution
```

执行计划把数据采集、行情/财务计算、周期序列、估值公式、模拟账本和基准归因固定为本地
确定性任务；模型只允许处理产品应用语义、产业关系判断、证据冲突解释、结论合成和对抗审查。
`LOCAL_ONLY` 只更新事实投影、规则状态和受影响模块，保留最后锁定结论，不凭空生成新的 AI
观点；预算耗尽自动转为 `LOCAL_ONLY`。网页 AI 仍只接受人工粘贴，不会被执行计划自动调用。

## 第三方基础组件适配器

第三方项目不直接进入事实层或决策层。先校验组件注册表：

```bash
PYTHONPATH=src python -m industry_first_research third-party-components \
  --input config/third_party_components.v1.json \
  --output-dir data/third_party_components \
  --candidate-review data/third_party_candidate_reviews/<review-or-projection>.json

PYTHONPATH=src python -m industry_first_research third-party-health \
  --registry data/third_party_components/default-third-party-components.json \
  --checked-at 2026-07-24T10:00:00+08:00 \
  --output-dir data/third_party_components
```

健康检查只说明本机可选包是否安装，不测试远端接口，也不表示数据抓取成功。当前环境未安装
`pypdf`、`pdfplumber`、`Camelot` 和 `quantstats` 时，结果会明确标记不可用；核心研究不会因此停止。

组件注册项必须保存候选评审 ID、能力切片、适配器注册 ID、夹具、基线和回退信息。传入一个或多个
`--candidate-review` 时，注册表还会逐项核对评审投影的状态和这些字段；只有 `ACCEPTED` 或满足明确条件的
`CONDITIONAL` 切片才允许启用。未完成评审的候选可以登记，但必须保持 `enabled=false`。

本地 PDF 解析必须由用户提供原始文件：

```bash
PYTHONPATH=src python -m industry_first_research third-party-parse \
  --component pdfplumber \
  --input data/source_inputs/<annual-report.pdf> \
  --document-id annual-report-2025 \
  --research-as-of 2026-07-24 \
  --output-dir data/third_party_document_parses
```

输出会保留原始文件哈希、页码/坐标、提取文本哈希、表格定位、组件版本和失败状态。解析成功不等于
财务事实核验成功，后续仍需进入 `source-document` 和 `evidence` 流程。

收益和风险统计支持量化统计库优先、本地计算回退：

```bash
PYTHONPATH=src python -m industry_first_research performance-metrics \
  --input data/third_party_performance_inputs/<input>.json \
  --output-dir data/third_party_performance
```

该命令只计算收益、年化收益、最大回撤、波动和超额收益等观察性统计，不改变决策快照、锁定基准或
因果归因结果。完整复用边界见 [`docs/decisions/0005-optional-third-party-component-adapters.md`](docs/decisions/0005-optional-third-party-component-adapters.md)。

### 外部项目候选评审

发现新的 GitHub/PyPI 项目时，先按能力切片建立候选评审，不自动下载或安装整个仓库：

```bash
# 创建 DISCOVERED 候选评审
PYTHONPATH=src python -m industry_first_research third-party-candidate-review \
  --input config/third_party_candidate_review.example.json \
  --output-dir data/third_party_candidate_reviews

# 追加一个不可变状态事件，并生成状态投影
PYTHONPATH=src python -m industry_first_research third-party-candidate-review-event \
  --review data/third_party_candidate_reviews/candidate-review-example-pdf-text.json \
  --input data/third_party_candidate_reviews/<event>.json \
  --events data/third_party_candidate_reviews/<previous-events>.json \
  --output-dir data/third_party_candidate_reviews

# 校验评审、事件或投影
PYTHONPATH=src python -m industry_first_research validate-third-party-candidate-review \
  --input data/third_party_candidate_reviews/<review-or-event-or-projection>.json
```

评审状态依次为 `DISCOVERED`、`CAPABILITY_SCOPED`、`LICENSE_AND_SECURITY_REVIEWED`、
`FIXTURE_VALIDATED`、`ADAPTER_PILOTED`，最后进入 `ACCEPTED`、`CONDITIONAL`、
`REFERENCE_ONLY` 或 `REJECTED`。评审记录和运行组件注册表是两类对象；一个项目的单个能力切片通过，
不代表整个仓库、交易接口或默认数据源可以使用。状态事件会校验前一事件的哈希、状态转移、时间顺序和
夹具/基线/回退条件；所有命令均为本地只读治理操作，不联网、不登录、不连接交易账户。

## 文档

- [`outputs/投研分析系统-需求文档.md`](outputs/投研分析系统-需求文档.md)
- [`outputs/投研分析系统-设计文档.md`](outputs/投研分析系统-设计文档.md)
- [`outputs/投研分析系统-评审记录-2026-07-17.md`](outputs/投研分析系统-评审记录-2026-07-17.md)
- [`docs/decisions/0002-external-ai-research-input.md`](docs/decisions/0002-external-ai-research-input.md)
- [`docs/decisions/0003-free-cross-platform-data-sources.md`](docs/decisions/0003-free-cross-platform-data-sources.md)
- [`docs/decisions/0005-optional-third-party-component-adapters.md`](docs/decisions/0005-optional-third-party-component-adapters.md)

网页 AI 说明：豆包、腾讯元宝、DeepSeek 等网页产品只通过 `MANUAL_WEB_AI` 模式人工导入。它们适合发现资料和提出反证，不进入自动行业雷达，也不能单独支撑关键事实、候选升级或模拟决策。

数据源说明：首期不依赖 QMT 或券商终端。交易所/公司披露、东方财富、AKShare、BaoStock 采用可配置主备链路；某个来源失败、限流或字段不完整时自动尝试下一个来源，所有尝试和第三方库诊断都会写入快照，全部失败才降级为“数据不足”。健康快照只记录适配器就绪、能力和失败原因，不能替代真实抓取。可选数据源的连接日志会被采集层捕获，不污染 CLI 的 JSON 输出。

## 免责声明

本项目只生成研究辅助内容和模拟决策记录，不构成投资建议，不执行真实交易。用户应自行核验数据和承担研究、模拟操作及传播风险。
