# Polymarket Tail-End Arb V5.1 — Backtest + Live Trading

Polymarket 二元预测市场的**尾端套利系统**。回测验证策略，实盘执行交易。核心策略逻辑双模共享，确保回测验证的就是实盘执行的。

## 策略核心逻辑

```
当一个二元事件结果已基本确定（价格 0.94-0.99），距离结算 < 12 小时时：
  → 以 Maker 限价单买入 YES Token（零手续费）
  → 等待价格上涨至 0.99 止盈，或持有至结算获得 $1.00
  → 若价格跌破 0.85，紧急 Taker 止损退出
```

## 回测结果 (V5.1)

| 指标 | 值 |
|------|-----|
| 总交易数 | 271 |
| 胜率 | **85.6%** |
| 总收益率 | **+2.36%** (2 个月) |
| 年化收益率 | +32.88% |
| 最大回撤 | 0.00% |
| 平均持仓 | 3.8 小时 |

## 项目结构

```
poly/
├── run_backtest.py             # 回测入口
├── run_live.py                 # 实盘入口
├── requirements.txt
├── .env.example                # 凭证模板
├── scripts/
│   └── setup_credentials.py    # 一键派生 API 凭证
├── src/
│   ├── config.py               # 策略参数 + 凭证配置
│   ├── models.py               # 共享数据模型
│   ├── strategy.py             # ★ 纯策略逻辑（双模共享核心）
│   ├── utils.py                # 工具函数
│   ├── backtest/
│   │   ├── engine.py           # 回测引擎
│   │   ├── data_fetcher.py     # 历史数据获取 + 缓存
│   │   └── analytics.py        # 性能分析 + 绘图
│   └── live/
│       ├── client.py           # CLOB 客户端封装 + DRY_RUN
│       ├── scanner.py          # 实时市场扫描
│       ├── executor.py         # 订单执行 + 生命周期管理
│       ├── monitor.py          # 持仓监控 + 止损看门狗
│       └── risk.py             # 风控熔断器
├── data/                       # [gitignored] API 数据缓存
├── output/                     # [gitignored] 回测报告
└── logs/                       # [gitignored] 运行日志
```

## 快速开始

### 1. 安装

```bash
git clone https://github.com/zw008/poly.git
cd poly
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 运行回测

```bash
python run_backtest.py
python run_backtest.py --capital 5000 --pages 50 --refresh
```

首次运行从 Polymarket API 拉取数据（约 5-10 分钟），之后读缓存秒级完成。

### 3. 实盘交易

#### 准备工作

1. **Polygon 钱包**：准备一个有 USDC.e 余额的 Polygon 钱包
2. **配置凭证**：

```bash
cp .env.example .env
# 编辑 .env，填入钱包私钥
vim .env
```

3. **派生 API 凭证**：

```bash
python scripts/setup_credentials.py
```

#### 运行（DRY_RUN 模式）

默认 `DRY_RUN=true`，不会提交真实订单：

```bash
python run_live.py --capital 1000
```

#### 运行（实盘模式）

修改 `.env` 中 `DRY_RUN=false`，然后：

```bash
python run_live.py --capital 1000
```

按 `Ctrl+C` 优雅退出（撤销所有挂单，保留持仓等待结算）。

## 安全机制

| 机制 | 说明 |
|------|------|
| DRY_RUN | 默认开启，逻辑正常运行但不提交订单 |
| 熔断器 | 累计亏损 >$500 或 >10% → 停止开仓 |
| 连续亏损 | 连续 10 次亏损 → 停止开仓 |
| 优雅退出 | SIGINT → 撤所有挂单，不强平持仓 |
| Maker-Only | 入场使用 POST_ONLY 限价单，零手续费 |

## 策略参数

所有参数集中在 `src/config.py`：

| 参数 | 值 | 说明 |
|------|-----|------|
| 入场价格 | 0.94 - 0.99 | YES Token 价格区间 |
| 时间窗口 | < 12 小时 | 距结算时间上限 |
| 止盈价格 | 0.99 | Maker 限价卖出 |
| 硬止损 | 0.85 | 确认后 Taker 止损 |
| 单笔仓位 | $50 | 固定金额 |
| 最大同类持仓 | 5 | 同一类目上限 |
| 最大总持仓 | 50 | 并行持仓上限 |

## 架构设计

```
strategy.py（纯函数，无副作用）
    ↑                    ↑
backtest/engine.py    live/executor.py + scanner.py + monitor.py
    ↑                    ↑
run_backtest.py       run_live.py
```

`strategy.py` 是核心 — 所有决策逻辑（入场判断、止盈止损、黑名单、分层分类）都在这里，回测和实盘共用同一套代码。

## 数据源

| API | 用途 |
|-----|------|
| [Gamma API](https://gamma-api.polymarket.com) | 市场列表、元数据 |
| [CLOB API](https://clob.polymarket.com) | 价格历史、订单簿、下单 |

## License

MIT
