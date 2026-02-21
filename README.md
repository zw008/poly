# Polymarket Tail-End Arb V5.1 — Backtest System

Polymarket 二元预测市场的**尾端套利回测系统**。利用市场结算前的定价低效（Favorite-Longshot Bias），在高概率事件的"最后一英里"以 Maker 零手续费进场，赚取确定性溢价。

## 策略核心逻辑

```
当一个二元事件结果已基本确定（价格 0.94-0.99），距离结算 < 12 小时时：
  → 以 Maker 限价单买入 YES Token（零手续费）
  → 等待价格上涨至 0.99 止盈，或持有至结算获得 $1.00
  → 若价格跌破 0.85，紧急 Taker 止损退出
```

**为什么能赚钱？** 市场上大量散户在结算前恐慌抛售高概率事件的 YES Token，导致 0.94-0.99 区间出现短暂的低效定价。本策略系统性地捕捉这些机会。

## 回测结果 (V5.1)

| 指标 | 值 |
|------|-----|
| 总交易数 | 269 |
| 胜率 | **87.7%** |
| 总收益率 | **+2.64%** (2 个月) |
| 年化收益率 | +37.29% |
| 最大回撤 | 2.24% |
| Profit Factor | 1.59 |
| Sharpe Ratio | 正 |
| 平均持仓 | 3.8 小时 |
| 总手续费 | $5.40 |

## 策略参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 入场价格 | 0.94 - 0.99 | YES Token 价格区间 |
| 时间窗口 | < 12 小时 | 距结算时间上限 |
| 止盈价格 | 0.99 | Maker 限价卖出 |
| 硬止损 | 0.85 | 1 根 K 线确认后 Taker 止损 |
| 单笔仓位 | $50 | 固定金额 |
| 入场手续费 | 0% | Post-Only Maker 单 |
| 止损手续费 | 0.5% | Taker 紧急退出 |
| 最大同类持仓 | 5 | 同一类目上限 |
| 最大总持仓 | 50 | 并行持仓上限 |

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/zw008/poly.git
cd poly
```

### 2. 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate    # macOS / Linux
# .venv\Scripts\activate     # Windows
pip install -r requirements.txt
```

### 3. 运行回测

```bash
python run_backtest.py
```

首次运行会从 Polymarket API 拉取数据（约 5-10 分钟），之后会缓存到 `data/` 目录。

### 命令行参数

```bash
python run_backtest.py --capital 10000  # 初始资金（默认 $10,000）
python run_backtest.py --pages 50       # API 拉取页数（默认 100，每页 100 个市场）
python run_backtest.py --refresh        # 强制重新拉取数据（忽略缓存）
```

### 4. 查看结果

回测完成后，结果输出到 `output/` 目录：

```
output/
├── report.txt          # 文字报告（终端同时打印）
└── equity_curve.png    # 权益曲线图
```

## 项目结构

```
poly/
├── run_backtest.py      # 主入口：组装管线，执行回测，输出报告
├── config.py            # 策略参数配置（可直接修改调参）
├── models.py            # 数据模型：Market, Position, Portfolio, PricePoint
├── data_fetcher.py      # Polymarket API 数据获取 + 本地缓存
├── backtest_engine.py   # 回测引擎：入场/出场/止损/结算模拟
├── analytics.py         # 性能分析：Sharpe, MaxDD, 分层报告, 权益曲线
├── requirements.txt     # Python 依赖
├── .gitignore
├── data/                # [自动生成] API 数据缓存
│   ├── markets.json     # 已结算市场元数据
│   └── prices/          # 各市场价格历史 {token_id}.json
└── output/              # [自动生成] 回测结果
    ├── report.txt
    └── equity_curve.png
```

## 数据源

| API | 用途 | 速率限制 |
|-----|------|----------|
| [Gamma API](https://gamma-api.polymarket.com) | 已结算市场列表、元数据 | 300 req/10s |
| [CLOB API](https://clob.polymarket.com) | 每个市场的价格时间序列（1h 粒度） | 1500 req/10s |

数据全部缓存到本地 `data/` 目录，支持断点续拉。第二次运行直接读缓存，秒级完成。

## 调参指南

所有策略参数集中在 `config.py`，可直接修改后重跑回测：

```python
# 调整入场范围
TIER_A = TierConfig(
    price_low=0.940,     # 入场下界
    price_high=0.990,    # 入场上界
    max_hours_to_resolution=12,  # 最长持仓时限
    position_size_usd=50.0,      # 单笔金额
    hard_stop_loss=0.85,         # 硬止损线
)

# 调整止盈
TAKE_PROFIT_PRICE = 0.99

# 调整持仓限制
MAX_SAME_CATEGORY = 5
MAX_CONCURRENT_POSITIONS = 50
```

## 策略迭代历史

| 版本 | 交易数 | 胜率 | 收益率 | 关键变更 |
|------|--------|------|--------|----------|
| V4.0 | 10 | 70% | -0.22% | 基线 |
| V5.0 | 398 | 78.6% | -3.22% | 加入 Tier B（失败） |
| **V5.1** | **269** | **87.7%** | **+2.64%** | **砍掉 Tier B + 止损 0.85** |
| V5.0 Prod | 189 | 91% | +0.02% | 缩窄入场，恢复 B（归零） |
| V7.0 | 105 | 100% | +1.57% | 动量过滤 + 熔断器 |

V5.1 综合收益最优，是当前推荐的生产参数。

## 核心风险

1. **高胜率依赖**：87.7% 的胜率需要长期维持，1 次硬止损 ≈ 16.5 次止盈
2. **样本期短**：仅 2 个月数据，未覆盖极端事件
3. **Maker 成交假设**：回测假设 Post-Only 限价单 100% 成交，实际可能部分未成交
4. **1h 粒度局限**：真实 30 秒止损确认用 1 小时 K 线模拟（保守估计）

## License

MIT
