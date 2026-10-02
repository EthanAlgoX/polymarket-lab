# Polymarket Lab

[English](README.md)

本地运行的 Polymarket 研究台：按行业浏览开放市场、查看公开订单簿，并计算考虑费用和深度的模拟机会。市场目录、交易空间、开源参考、盘口扫描、运行监控、历史和参数页共用响应式侧边栏。

行情直接来自 Polymarket 官方 API，不抓取网页 HTML、不使用第三方报价。项目不连接钱包、不签名、不提交订单、不转移资金；净差是公开快照的模拟结果，不代表真实成交或保证盈利。

## 快速启动

需要 Python 3.11 或更新版本，推荐 Python 3.12。

```sh
git clone https://github.com/EthanAlgoX/polymarket-lab.git
cd polymarket-lab
```

macOS：

```sh
./start-local.command
```

首次启动会创建本项目的 `.venv` 并安装锁定依赖。未继承翻译密钥时，启动脚本会加载用户的交互式 zsh 环境。

Linux 或手动启动：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。首次发现市场在后台运行，需要一些时间。也提供 Windows 的 `install.bat` / `run.bat` 和 `docker compose up --build`。

## 数据与研究范围

- 目录读取 Gamma `/events/keyset`，先提供热门、最新和分类样本，再遍历最多 100 页、每页最多 100 个事件；每轮完成后约十分钟重新发现。页面显示覆盖状态和失败，达到上限不意味着完整收录全站。
- 分类包括体育、天气、加密、经济/金融、政治和其他，依据事件标签归类。标签、成交量和流动性用于筛选，不等于盈利信号。
- 扫描器监控有限数量的 Yes/No 市场，由 `PMS_MAX_MARKETS` 配置。CLOB `/books` 默认五秒刷新一次；公开 Market WebSocket 订阅选定 token，净差计算仍使用 REST 快照。
- 详情保留结果/token对应顺序，也支持队名、Up/Down 等二元结果。金融计算使用 `Decimal`，检查深度、手续费、报价时间、最小成交量和费用缓冲；费用未知或不支持时不认定有效机会。
- 模拟记录、历史和 CSV 导出保存在本地。交易空间页提供候选研究方向；外部天气观测、体育赔率、经过校准的预测模型和真实交易尚未实现。

## 可选中文翻译

默认中文，切换 English 可恢复官方原文。配置 DeepSeek 后，可见的标题、事件、结果和展开规则自动翻译；新出现或原文变化的文本也会处理。

后端读取环境变量或被忽略的本地 `.env` 中的 `DEEPSEEK_API_KEY`，也兼容 `DEEPSEEK_KEY` / `PMS_DEEPSEEK_API_KEY`。可选 `DEEPSEEK_API_BASE` 仅接受官方 `https://api.deepseek.com` 或 `https://api.deepseek.com/v1`。

模型为 `deepseek-flash`（DeepSeek V4.1 Flash），是 2026-10-02 核实的官方 API 最便宜可用模型，关闭思考模式。仅批量翻译当前可见文本，缓存到 `data/translations.sqlite3`；有限纠正重试仍用同一模型，不自动升级到更贵的模型。新文本首次翻译消耗提供商账户额度。缺少密钥或翻译失败时保留原文并显示状态。

密钥仅在后端使用。翻译只改变显示文本，计算、价格、ID和结果/token顺序使用原始数据；结算请核对英文原文。搜索和 CSV 导出目前仍使用原文。

## 配置与验证

应用配置使用 `PMS_` 前缀，见 `.env.example` 和参数页。运行数据在 `data/`、`logs/`；密钥、`.venv`、数据库、日志、导出和缓存不应提交到 Git。

```sh
python -m pip install -r requirements-dev.txt
ruff check .
ruff format --check .
mypy app
python -m pytest
python scripts/security_scan.py
```

默认测试使用模拟数据并排除在线测试。`python -m pytest -m live` 明确验证公开 Polymarket 接口；测试不需要钱包或付费翻译调用。

## 许可与来源

MIT 许可。采集和扫描底座来自 [0106ss/polymarket-market-scanner](https://github.com/0106ss/polymarket-market-scanner)，上游提交 `587daca8548f6c737b4d642b49c9f000247361ab`。原版权和许可保留在 [LICENSE](LICENSE)，改动见 [UPSTREAM.txt](UPSTREAM.txt)。界面列出的其他开源项目仅作研究参考，未集成其代码。

贡献和安全说明见 [CONTRIBUTING.md](CONTRIBUTING.md) / [SECURITY.md](SECURITY.md)。
