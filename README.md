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
- 白酒行业配置化纵向切片：行业雷达、13 家代表公司池、5 家深度层、Markdown/HTML 报告和 JSON 快照。
- 确定性的周期反转/质量修复规则审计，以及公司淘汰、空结果和研究资产缺失留痕。
- 交易所/公司披露、东方财富、AKShare、BaoStock 的可插拔适配器和主备路由；连接失败、超时、限流、空结果或字段不完整会自动切换并保留尝试记录。
- 通威股份 `600438.SH` 公司研究配置化纵向切片：公司身份、业务范围、产品画像、财务和行情按字段主备采集，并输出 `READY/PARTIAL/INSUFFICIENT` 状态。

尚未完成：

- `luopan` / `ai-berkshire` 的字段级研究资产导入；
- 各交易所和上市公司披露站点的具体 URL/解析模板，以及更完整的行业数据配置；
- 产品级深研、模拟决策快照和持续跟踪；
- Web 界面和微信公众号草稿发布。

## 开发

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
python -m industry_first_research demo

# 可选免费数据依赖（Mac/Linux/Windows 均可）
python -m pip install -e '.[data]'
```

也可以直接运行：

```bash
PYTHONPATH=src python -m industry_first_research demo

# 白酒行业纵向切片
PYTHONPATH=src python -m industry_first_research industry \
  --config config/industries/baijiu.json \
  --output /tmp/baijiu-report.md \
  --html-output /tmp/baijiu-report.html

# 通威股份公司快照（按交易所/公司披露、东方财富、AKShare、BaoStock 主备切换）
PYTHONPATH=src python -m industry_first_research company \
  --config config/companies/600438.json
```

## 外部研究资产

本地 `vendor/luopan` 和 `vendor/ai-berkshire` 是用于开发和研究验证的上游工作树。由于本仓库是公开仓库，当前不自动提交其中的历史报告、数据和完整工作树；来源版本记录在 [`vendor/SOURCES.md`](vendor/SOURCES.md)。后续会通过适配器引用或按许可证明确允许的内容接入。

## 文档

- [`outputs/投研分析系统-需求文档.md`](outputs/投研分析系统-需求文档.md)
- [`outputs/投研分析系统-设计文档.md`](outputs/投研分析系统-设计文档.md)
- [`outputs/投研分析系统-评审记录-2026-07-17.md`](outputs/投研分析系统-评审记录-2026-07-17.md)
- [`docs/decisions/0002-external-ai-research-input.md`](docs/decisions/0002-external-ai-research-input.md)
- [`docs/decisions/0003-free-cross-platform-data-sources.md`](docs/decisions/0003-free-cross-platform-data-sources.md)

网页 AI 说明：豆包、腾讯元宝、DeepSeek 等网页产品只通过 `MANUAL_WEB_AI` 模式人工导入。它们适合发现资料和提出反证，不进入自动行业雷达，也不能单独支撑关键事实、候选升级或模拟决策。

数据源说明：首期不依赖 QMT 或券商终端。交易所/公司披露、东方财富、AKShare、BaoStock 采用可配置主备链路；某个来源失败、限流或字段不完整时自动尝试下一个来源，所有尝试和第三方库诊断都会写入快照，全部失败才降级为“数据不足”。可选数据源的连接日志会被采集层捕获，不污染 CLI 的 JSON 输出。

## 免责声明

本项目只生成研究辅助内容和模拟决策记录，不构成投资建议，不执行真实交易。用户应自行核验数据和承担研究、模拟操作及传播风险。
