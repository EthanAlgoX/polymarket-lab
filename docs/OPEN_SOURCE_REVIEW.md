# Polymarket 开源项目筛选与优化记录

检索日期：2026-10-03（Asia/Shanghai）。Star 数来自本次 GitHub REST API 快照；源码阅读固定到以下提交，未运行第三方交易代码。以此前项目池中 **≥200 stars** 为筛选线，得到 5 个项目，另补充官方 CLI、prediction-market-analysis 和 PMXT，共 8 个。Star 反映关注度，归档状态、接口兼容性和实际代码更影响采用决策。

| 项目 | Stars | 许可证 | 已归档 | 可借鉴内容 | 本轮决定 |
| --- | ---: | --- | --- | --- | --- |
| [poly-maker](https://github.com/warproxxx/poly-maker) | 1,503 | MIT | 否 | 盘口指标、行情状态、事件记录 | 独立实现盘口指标 |
| [py-clob-client](https://github.com/Polymarket/py-clob-client) | 1,226 | MIT | 是 | 批量盘口、元数据缓存 | 历史参考，不采用旧 SDK |
| [clob-client](https://github.com/Polymarket/clob-client) | 514 | MIT | 是 | 类型边界、分页、错误结构 | 历史参考，不采用旧 SDK |
| [real-time-data-client](https://github.com/Polymarket/real-time-data-client) | 228 | MIT | 否 | 连接状态、订阅生命周期 | 借鉴结构，不加入依赖 |
| [polymarket-subgraph](https://github.com/Polymarket/polymarket-subgraph) | 218 | LGPL-3.0 | 否 | 链上历史、成交量和标识口径 | 后续研究，不复制代码 |
| [官方 polymarket-cli](https://github.com/Polymarket/polymarket-cli) | 2,875 | 完整许可未核验 | 否 | 市场筛选、结构化输出 | 补充流程参考 |
| [prediction-market-analysis](https://github.com/Jon-Becker/prediction-market-analysis) | 3,854 | MIT | 否 | 历史分块、HTTP 池、暂时故障重试 | 调研参考，未导入历史集 |
| [PMXT](https://github.com/pmxt-dev/pmxt) | 2,166 | MIT | 否 | 真实 outcome 盘口、统一数据结构 | 概念参考，不加入聚合 SDK |

源码发现与取舍：

- **poly-maker**：`4f321035` 的 [orderbook.py](https://github.com/warproxxx/poly-maker/blob/4f32103591c9582ccd012bdf10f77d86e5879444/src/polymaker/marketdata/orderbook.py) 提供 spread、imbalance 和 microprice。参考这些描述性指标，改用 Decimal 并定义清晰的深度范围；不引入其 float 计算、钱包和做市执行。指标描述当前盘口，不代表真实概率或预期利润。
- **py-clob-client**：`b076b04d` 的 [client.py](https://github.com/Polymarket/py-clob-client/blob/b076b04d61135657e25dccc1bbd6866a96bd8c6e/py_clob_client/client.py) 展示批量读取和 tick 缓存。可借鉴缓存失效思路；仓库已归档，其旧费率默认值和长期缓存不能替代本项目的未知费率拦截。
- **clob-client**：`7df8257d` 的 [client.ts](https://github.com/Polymarket/clob-client/blob/7df8257dc95f99edb257b53a7873e273a9b4a9b3/src/client.ts) 提供盘口与分页接口。参考输入输出边界，避免把失败响应当正常数据；旧客户端已归档，不能因 star 较高继续采用。
- **real-time-data-client**：`c937d9c` 的 [client.ts](https://github.com/Polymarket/real-time-data-client/blob/c937d9c11cdd2b771aa4818392a1b6dda65c25de/src/client.ts) 区分连接状态并提供订阅回调，但自动重连没有退避。它连接 RTDS，不能直接替代 CLOB 盘口流；本项目保留自己的公共行情客户端。
- **polymarket-subgraph**：`7a92ba0` 的 [schema](https://github.com/Polymarket/polymarket-subgraph/blob/7a92ba026a9466c07381e0d245a323ba23ee8701/orderbook-subgraph/schema.graphql) 区分成交次数、原始金额和缩放金额。其 `Orderbook` 实体是成交汇总，不是当前挂单深度。借鉴指标口径，LGPL 源文件没有并入本项目。
- **官方 CLI**：`9b18b5fa` 的 [markets.rs](https://github.com/Polymarket/polymarket-cli/blob/9b18b5faf5493b945c48ca22efaf9645f0c69ab8/src/commands/markets.rs) 可参考列表、筛选、详情流程。README 声明 MIT，但该提交树未发现 LICENSE 文件、GitHub 许可字段为空，因此不据此复制源码。
- **prediction-market-analysis**：`5690e332` 的 [markets.py](https://github.com/Jon-Becker/prediction-market-analysis/blob/5690e332b0778c6e21986accfba67a3a4b8f3ac2/src/indexers/polymarket/markets.py) 分块写 Parquet，[HTTP client](https://github.com/Jon-Becker/prediction-market-analysis/blob/5690e332b0778c6e21986accfba67a3a4b8f3ac2/src/common/client.py) 复用连接池、限制速率并重试暂时故障。可参考未来历史存储；其 [market client](https://github.com/Jon-Becker/prediction-market-analysis/blob/5690e332b0778c6e21986accfba67a3a4b8f3ac2/src/indexers/polymarket/client.py) 使用 limit/offset，不能称为 keyset。本轮未下载历史集、未做回测。
- **PMXT**：`4a367d81` 的 [fetchOrderBook 示例](https://github.com/pmxt-dev/pmxt/blob/4a367d812541154002eedda36b0916a3cf68e0f2/core/examples/api-reference/market-data/fetchOrderBook.ts) 按真实 outcome ID 取盘口，返回标准 bids/asks，支持我们保留各 token 独立结构的选择。其 [pagination test](https://github.com/pmxt-dev/pmxt/blob/4a367d812541154002eedda36b0916a3cf68e0f2/core/test/pipeline/kalshi-pagination.test.ts) 验证的是 Kalshi，不能作为 Polymarket 分页保证；未引入聚合 SDK。

另以未归档的 [py-sdk](https://github.com/Polymarket/py-sdk)（131 stars）作为当前兼容性基准：`b543c9db` 的 [transport](https://github.com/Polymarket/py-sdk/blob/b543c9db0c896a3727619ea174db7971f03b5b6a/src/polymarket/clients/_transport.py) 解析限流信息，[pagination](https://github.com/Polymarket/py-sdk/blob/b543c9db0c896a3727619ea174db7971f03b5b6a/src/polymarket/pagination.py) 区分分页结束与达到上限。SDK 本身不自动重试；本项目的重试政策由我们独立实现。

本轮落实的优化：

1. 每个真实 outcome/token 独立计算 Decimal 盘口摘要，展示价差、最优档不平衡、microprice 和两侧 2 分范围深度；空盘、单边和交叉盘不生成误导指标。
2. WebSocket 按完整规范化消息去重，缓存有上限；同一时间戳的不同增量保留，重连后允许初始快照重新交付。
3. 公共请求识别服务端等待时间、共享冷却并限制重试；错误保留可诊断状态，排除响应正文和敏感查询内容。
4. 目录刷新按完整修订原子发布，拦截重复游标，明确覆盖上限与停止原因；先按流动性及最低成交量门槛筛选，再分配分类名额，最后按活跃度补齐。
5. 开源参考页新增“高星”“未归档”“全部”筛选和逐项采用决定；运行监控展示 HTTP 请求、重试与限流计数。
6. 盘口描述和机会判断共用 Decimal 时间校验，拒绝缺失、非有限、非正数及超过 1 秒的未来时间；详情只按请求的两腿判断年龄和最小数量。

深度数量单位为份额，抵押金额为“价格 × 份额”；不把它们与历史美元成交额混用。microprice 由最优买卖价和对侧挂单量加权得到，仍需结合真实成交深度、费用与行情年龄判断。HTTP 冷却针对限流和暂时故障，永久失败不会持续重试。目录达到页数上限仍表示覆盖不完整，刷新失败保留最近一次已发布的数据，并显式报告失败原因。

这些优化是概念参考后的独立实现，没有集成第三方 SDK 的交易代码。最初实际复用的基础仍是 `0106ss/polymarket-market-scanner`，原有 [UPSTREAM.txt](../UPSTREAM.txt) 与 MIT 来源声明保留。

官方 [agents](https://github.com/Polymarket/agents) 虽有 3,796 stars，但已归档，最后推送于 2024 年，且偏自动交易，本轮排除实现采用。

验证状态：本轮 150 项本地测试通过（应用覆盖率 86%）；另外实际运行的 1 项在线测试通过，连接公开 Gamma、CLOB 和 Market WebSocket。Ruff 检查与格式检查、mypy、JavaScript 语法和安全扫描均通过。新版本已在本地启动，验证高星筛选的 8/6/15 个项目、实时双腿指标、监控请求计数和六行业的 80 个扫描样本；桌面 1280px、手机 390px 下页面没有横向溢出，指标表可在容器内滚动，共享导航保持可用。
