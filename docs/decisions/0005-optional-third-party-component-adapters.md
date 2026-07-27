# 决策记录 0005：第三方基础组件采用可选适配器

## 状态

已决定，2026-07-24 生效。

## 背景

需求和设计文档要求优先复用成熟开源项目，但本系统的核心不是量化交易框架，而是行业优先研究、证据血缘、时间截面、模拟决策和结果归因。把大型平台整体引入会扩大依赖、许可证、数据口径和交易边界风险。

## 决策

第三方项目只按能力通过适配器或隔离进程接入，统一使用：

```text
DIRECT_REUSE
ADAPTER_REUSE
FORK_AND_MODIFY
REFERENCE_ONLY
```

首批代码落地：

- `pypdf`、`pdfplumber`、`Camelot`：本地 PDF 文本/表格提取候选；未安装时明确降级，不联网、不把提取结果升级成事实；
- `quantstats`：收益、回撤、波动统计候选；未安装时使用本地确定性计算，不替代锁定基准和归因；
- `APScheduler`、`DuckDB`、`Polars`：仅记录为后续条件适配，不进入本次默认运行链路；
- Qlib、OpenBB、vn.py、QUANTAXIS 等大型平台：当前仅作参考，不整体引入。

## 实现

- `src/industry_first_research/third_party_components.py` 提供注册表、健康快照、PDF 适配器和绩效统计适配器；
- 运行组件注册项保存 `candidate_review_id`、能力切片、评审状态、适配器注册 ID、夹具、基线和回退；`validate_component_registry_links` 可将注册表与候选评审/投影逐项核对；
- `build_component_registration_from_candidate` 只允许 `ACCEPTED`/`CONDITIONAL` 评审生成可启用注册项，不接受未完成评审或无夹具/基线/回退的候选；
- `config/third_party_components.v1.json` 保存组件版本、许可证状态、依赖、时间截面和回退声明；
- 所有适配器输出包含组件标识、原始输入哈希、解析/计算版本、状态和只读策略；
- `third-party-health` 只检查本地可选依赖，不代表远端服务可用；
- 组件缺失或升级失败不会影响证据、确定性模型、研究版本、模拟账本和报告读取。
- `src/industry_first_research/third_party_candidate_review.py` 提供按能力切片的候选评审、状态事件和投影；候选评审不等于安装或运行注册，只有验收通过的切片才可被运行注册表引用；
- `third-party-candidate-review`、`third-party-candidate-review-event` 和 `validate-third-party-candidate-review` CLI 只读本地 JSON，不自动下载、安装、联网、登录或连接交易账户；

## 影响

- 默认安装不增加 PDF、统计、调度或数据库依赖；
- 后续安装可选包时不需要改动研究核心；
- PDF 解析结果必须继续经过 `SourceDocument`/`Evidence` 的页码、哈希、时间截面和人工核验流程；
- 统计辅助结果只能作为观察性指标，不能直接生成投资结论或交易指令；
- 许可证或项目说明冲突时，组件进入 `LICENSE_REVIEW_REQUIRED`，不得静默商用。

候选评审状态采用：

```text
DISCOVERED → CAPABILITY_SCOPED → LICENSE_AND_SECURITY_REVIEWED
→ FIXTURE_VALIDATED → ADAPTER_PILOTED
→ ACCEPTED / CONDITIONAL / REFERENCE_ONLY / REJECTED
```

评审对象、状态事件和投影均不可变；同一项目的不同能力切片可以独立进入不同状态。运行注册项必须引用评审 ID、夹具、基线、适配器和回退实现，不能因为一个切片通过就接受整个仓库。
