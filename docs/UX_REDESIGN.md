# Workspace flow and UI redesign

Reviewed **2026-10-03 (Asia/Shanghai)**. This report covers the complete local research workspace: the catalog, research references, scanner, market inspection, paper observations, signal history, monitor, settings and logs. Earlier calculation/runtime evaluations remain in [FUNCTIONAL_AUDIT.md](FUNCTIONAL_AUDIT.md) and [FEATURE_EVALUATION.md](FEATURE_EVALUATION.md). API and financial contracts are in [API_REFERENCE.md](API_REFERENCE.md) and [CALCULATION.md](CALCULATION.md).

The main workflow is **discover a market → inspect its evidence → observe a qualifying scanner snapshot → revisit the saved inputs**. The catalog and scanner have different scopes. A catalog preview is a current cost estimate; a scanner candidate must additionally pass every configured gate. A saved paper observation keeps its recorded estimate, and reopening current inspection is a separate action.

## Function map

| Navigation / page | Data and operation | Result and boundary |
| --- | --- | --- |
| Discover → Markets, `/#markets` | Cached Gamma catalog; All/category tabs, source-text search, liquidity, sort, pagination; inspect a market | Counts and rows share one published revision. Applied filters/page remain attached to retained rows during a pending or failed refresh. Catalog refresh rereads the server snapshot; it does not force a whole-site crawl. Coverage may be sampled, capped or partial. |
| Discover → Strategies, `/#strategies` | Checked-in research hypotheses, required data, failure cases and source links | Reading material and next validation steps. External sports odds, weather observations and calibrated predictions are not connected. |
| Discover → Open source, `/#opensource` | Dated repository review; high-star, non-archived high-star and all filters | Inspectable references, attribution and adoption choices. Star counts are a review-time snapshot. |
| Catalog inspection drawer, `/#markets?inspect=ID` | Recheck current Gamma state/mapping, then read CLOB books; adjust local quantity/extra cost and read rules | Preserves original outcome/token order. Binary conditions receive an estimate; larger outcome sets receive descriptive books. Preview parameters do not change scanner settings or save observations. |
| Observe → Book scanner, `/opportunities` | Current bounded Yes/No selection; current diagnostics and passing candidates; inspect and save an observation | Fresh source books, supported known fees, known minimum size, complete depth, identity and net-profit/ROI gates are required. Save rechecks under the refresh lock. |
| Scanner market detail, `/markets/{id}` | Scanner estimate, explicit Yes/No display books and retained independent REST calculation inputs | Display books may be newer through WebSocket. Current candidate eligibility is separate from mathematical `VALID`. |
| Observe → Paper records, `/paper-trades` | Persisted observations; 100-row pagination, saved audit details, current inspection and complete CSV export | Estimates remain as recorded. Details retain parameters, original mappings and actual REST books when available; older missing audits are explicit. |
| Observe → Signal history, `/history` | Persisted scanner signals; first/last seen, maxima, observation state and saved audit details | `active`/`disappeared` describes historical observation lifecycle, not current execution permission. Independent maxima need not describe the same calculation; the saved snapshot is one calculation. Current inspection does not recalculate it. |
| Workspace → Monitor, `/monitor` | Local database, public API/WS state, bounded selection, source/fetch timing, errors and HTTP counters | Database health, transport connectivity and source freshness are independent. Repeated/overlapping paper estimates do not represent portfolio or account profit. |
| Workspace → Settings, `/settings` | User translation API; five scanner parameters with separate forms and explicit save states | Native localhost credential writes; Docker uses backend `.env`. Saving scanner parameters clears old calculations until the next successful refresh. English works without an API; Chinese requires one. |
| Workspace → Logs, `/logs` | Latest 100 local events, severity filter, manual refresh and pause/resume view updates | Pausing freezes automatic browser rereading. Backend polling and event persistence continue. |

## Audited problems and changes

| Problem in the previous interface | Why it mattered | Change |
| --- | --- | --- |
| Research and scanner pages used different visual shells and crowded headers | Navigation felt disconnected; global controls competed with page actions | Shared top bar, grouped navigation and consistent task headings, controls, tables and feedback. One global language switch remains available across pages. |
| Nine destinations lacked a clear sequence | Users had to infer how discovery, calculations, records and system tools fit together | Discover / Observe / Workspace groups retain existing URLs and organize the main research workflow. Narrow screens use an accessible menu rather than compressing every destination into the content area. |
| Catalog summary, coverage text and six large category blocks competed with the market table | Important scope information required reading a large introductory area before reaching usable data | Compact summary/category controls, adjacent filters and a clearer table-first hierarchy; detailed coverage and selection evidence remain available. |
| Changing filters or paging could leave old rows described by new requested controls after a failure | The displayed scope could no longer be trusted, especially during a language switch | Applied filter/page state stays aligned with the retained response. Failed refreshes mark older results and disable paging until retry; the catalog can still render if the separate monitor-status request fails. |
| Zero scanner results showed no quantitative explanation | A healthy sample with no edge resembled broken collection, unknown fees or expired quotes | Current diagnostics show selected / calculated / candidate counts and a partition of rejected markets by primary reason. Counts identify the bounded universe and expose actual runtime thresholds. |
| The candidate API duplicated a stored quote age and an updated nested quote age | Consumers could disagree about which age the candidate used | The top-level calculation now matches `market.calculation`; both use one observation time. Diagnostic candidate counts are assessed at that same time. |
| Structural rejection calculations carry zero executable quantity | A minimum-size explanation could conceal crossed books or invalid mappings | Diagnostic reasons preserve structural failures before interpreting zero-quantity sentinels. Eligibility gates and Decimal financial calculations remain unchanged. |
| Saved records had audit detail APIs but no direct UI entry | Users could not inspect the evidence behind an observation without manually constructing requests | Paper/history detail interactions expose saved inputs; a separate current-inspection link preserves the distinction between past evidence and current quotes. |
| Saving an observation used a blocking alert and offered a weak next step | The research flow stopped after saving instead of leading to review | Inline save feedback shows the saved ID and links to Paper records. Duplicate in-flight submissions remain guarded. |
| Live logs could move while being read | Troubleshooting required repeatedly finding an event | Pause/resume automatic view updates while retaining the severity filter. Pausing also discards an in-flight automatic result; manual refresh updates once while remaining paused. |
| Dense forms and always-expanded research/reference text obscured the next action | API setup, scanner parameters and reference reading competed for attention | Clear independent settings sections and progressively disclosed research/reference detail; draft/save/failure feedback remains attached to the corresponding form. Initial/repeated settings reads cannot overwrite drafts or a later save. Reference-fetch failures offer an inline retry. |
| Page and drawer backgrounds could remain keyboard-interactive | Keyboard focus could escape the active modal or mobile menu | Active overlays make background regions inert, constrain keyboard traversal, close with Escape and restore focus. Hidden content and reduced-motion preferences are respected. |

The visual system uses a daylight canvas, white work surfaces, ink text and restrained emerald actions. Status colors support text labels; they do not stand in for the underlying eligibility checks. Wide tables scroll within their own containers. Product and design decisions are recorded in [PRODUCT.md](../PRODUCT.md) and [DESIGN.md](../DESIGN.md).

## Diagnostic interpretation

Diagnostics describe **current selected scanner markets**, not all catalog markets. `calculated_count` includes unusable retained calculations. Every rejected selected market receives one primary reason, so `sum(reason_counts) = rejected_count` and `candidate_count + rejected_count = selected_count`. Several checks may fail for one market; the partition does not claim otherwise.

`checked_at` is assessment time; `calculation_as_of` is local REST receipt time. Source book timestamps determine freshness. A recently received quiet book can still be stale. Unknown source times, fees and minimum quantities fail closed. No additional candidate is introduced by the redesign, and zero candidates does not establish either a broken system or an absence of platform-wide opportunities.

Saved history states remain historical. A `SUCCESS` paper record means the local observation passed saving checks; it does not mean either leg traded. Current inspection may fail or show different prices while the saved audit remains available. CSV exports still include all saved rows, source text and explicit UTC timestamps.

### Final browser repairs

The phone acceptance pass identified two cross-page defects. Unversioned navigation assets could leave a returning browser running the former menu controller, so changed CSS/JS assets now share a new release suffix. An absolutely positioned screen-reader label inside a wide table escaped its clipping context and expanded the phone document to 817px; making the table scroll container positioned restored a 390px document without hiding data. Mobile focus is captured before making the toolbar inert and restored on Escape; keyboard traversal recovers inside the menu if native focus is lost. Snapshot buttons now say “View snapshot” / “查看快照” to distinguish reading existing evidence from saving a new observation.

## Verification evidence

Evidence is scoped to what actually ran. The redesign does not change wallet/trading capabilities, provider model defaults or persisted financial calculations.

| Check | Evidence / status |
| --- | --- |
| Backend diagnostics and current-age consistency | **Passed:** 81 targeted scanner, source-time, runtime-recovery and integration audit tests. New diagnostics tests include a nine-market partition, a real crossed-book calculation with zero quantity, a source timestamp that remains stale after a new receipt, and API age/count parity. |
| Backend lint, format and typing | **Passed:** Ruff checks/format and mypy for the changed backend files. |
| Catalog/reference frontend regression | **Passed:** 14 targeted Node VM cases, including applied-scope retention after failure, direct-inspection hash routing, and catalog/reference request recovery. These deterministic cases are not live browser or provider checks. |
| Complete regression suite and security | **Passed:** 439 tests, one opt-in live test deselected, 90% coverage (Python 3.12 / Node 22); Ruff, formatting, mypy, security scan and diff whitespace checks passed. The earlier 425-test evaluation remains historical. |
| Desktop/narrow-screen layouts and browser flows | **Passed:** 1280px desktop and 390px phone acceptance. Tested category filtering, catalog pagination, detail deep links and multi-outcome inspection, candidate save/feedback, paper/history audit panels and language retention, record pagination, unknown-fee blocking, missing-key Chinese gate, mocked API configuration, threshold draft/save/reload, search empty states, mobile menu/Escape and log pause/manual refresh. Phone document width equals 390px; tables scroll within their containers. Browser error logs were empty. [Live catalog](images/overview-en.png) and [English API settings](images/api-settings-en.png) screenshots were refreshed. Positive/translation cases used isolated synthetic fixtures, with no provider charges or writes to user settings. |
| Live public-data readiness | **Passed separately:** real local service served all seven page routes and `/health` with 200; Gamma/CLOB requests succeeded and Market WebSocket connected. Final observed sample contained 80 selected markets with zero candidates. During metadata refresh, diagnostics correctly reported awaiting calculations rather than reusing older eligibility. Connection health does not imply every quote is fresh or that an opportunity exists. |

Maintainers can reproduce positive and rejection paths with [the isolated fixture](../tests/manual/fixture_server.py) using the commands in the [English README](../README.md#maintainer-ui-acceptance-with-isolated-synthetic-data). All fixture markets and records are marked `[TEST]`; temporary databases and mock provider requests do not modify the user's data or consume LLM credits.

## Implemented scope and future research

The implemented scope is public market browsing, current book inspection, binary complete-set estimates, a bounded Yes/No scanner, auditable paper observations/history, diagnostics, local API configuration and bilingual display. English is the first-visit default. Chinese market text uses the user's configured backend LLM API; static Chinese documentation remains readable without one. Credentials remain local, ignored by Git and absent from API responses.

External predictive feeds, validated sector decision models, cross-platform/cross-event or multi-outcome arbitrage, full historical replay/backtesting, wallet balances and real trading remain future or unsupported work. The strategy/reference pages explain research possibilities without presenting them as implemented profitable strategies. Original MIT notices and source attribution remain retained.

### 中文概要

本次将网站流程整理为“发现市场 → 核验来源与盘口 → 保存观察 → 回看审计输入”，侧栏分为发现、观察、工作区三组。重点修复零候选缺少原因、重复计算年龄不一致、历史审计入口缺失、保存后流程中断、日志阅读被刷新打断及窄屏/键盘导航割裂。界面统一为浅色研究工作台，默认英文，中文仍要求自己的 LLM API。

诊断针对有限扫描样本，每个被拒绝市场只计一个主要原因；接口拉取时间不等于源盘口更新时间。保存记录只是当时估算，打开当前核验不会改变历史输入。真实交易、外部预测和回测等能力没有因为 UI 改造而新增。最终集成检查与浏览器证据按上表实际运行结果更新。
