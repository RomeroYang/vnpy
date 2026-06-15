#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
PORTFOLIO_SRC = Path("/Users/shawn/github/defintech/vnpy_portfoliostrategy")
if str(PORTFOLIO_SRC) not in sys.path:
    sys.path.insert(0, str(PORTFOLIO_SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from vnpy.trader.constant import Exchange, Interval  # noqa: E402
from vnpy.trader.object import BarData  # noqa: E402
from vnpy_portfoliostrategy import BacktestingEngine  # noqa: E402

from examples.claw_slow3d_dry_run.run_parity_backtest import (  # noqa: E402
    CONTRACTS,
    DEFAULT_AKQUANT_REPORT,
    DEFAULT_DATA_ROOT,
    DEFAULT_OUTPUT_ROOT,
    load_akquant_equity,
    load_akquant_metrics,
)
from examples.claw_slow3d_dry_run.strategies.target_weight_replay_strategy import TargetWeightReplayStrategy  # noqa: E402


EXCHANGE_MAP = {
    "SHFE": Exchange.SHFE,
    "DCE": Exchange.DCE,
    "CZCE": Exchange.CZCE,
    "INE": Exchange.INE,
    "GFEX": Exchange.GFEX,
}


def load_daily_bars(symbols: list[str], data_root: Path) -> dict[tuple[datetime, str], BarData]:
    history: dict[tuple[datetime, str], BarData] = {}
    for symbol in symbols:
        spec = CONTRACTS[symbol]
        vt_symbol = f"{symbol}.{spec.exchange}"
        frame = pd.read_csv(data_root / f"{symbol}-1d.csv", parse_dates=["datetime"])
        frame = frame.sort_values("datetime").drop_duplicates("datetime")
        for row in frame.itertuples(index=False):
            dt = pd.Timestamp(row.datetime).to_pydatetime()
            bar = BarData(
                symbol=symbol,
                exchange=EXCHANGE_MAP[spec.exchange],
                datetime=dt,
                interval=Interval.DAILY,
                open_price=float(row.open),
                high_price=float(row.high),
                low_price=float(row.low),
                close_price=float(row.close),
                volume=float(row.volume),
                gateway_name="CSV",
            )
            history[(dt, vt_symbol)] = bar
    return history


def normalize_vnpy_statistics(stats: dict) -> dict[str, float]:
    return {
        "total_return_pct": float(stats["total_return"]),
        "annualized_return": float(stats["annual_return"]) / 100.0,
        "max_drawdown_pct": abs(float(stats["max_ddpercent"])),
        "sharpe_ratio": float(stats["sharpe_ratio"]),
        "trade_count": float(stats["total_trade_count"]),
        "end_market_value": float(stats["end_balance"]),
        "total_commission": float(stats["total_commission"]),
        "turnover": float(stats["total_turnover"]),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run vn.py PortfolioStrategy parity backtest for claw slow3d target weights.")
    parser.add_argument("--target-weights", type=Path, default=DEFAULT_AKQUANT_REPORT / "target_weights.csv")
    parser.add_argument("--akquant-metrics", type=Path, default=DEFAULT_AKQUANT_REPORT / "metrics.csv")
    parser.add_argument("--akquant-equity", type=Path, default=DEFAULT_AKQUANT_REPORT / "equity_curve.csv")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--commission-rate", type=float, default=0.0001)
    parser.add_argument("--slippage-bps", type=float, default=2.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_weights = pd.read_csv(args.target_weights, parse_dates=["datetime"]).set_index("datetime")
    symbols = list(target_weights.columns)
    vt_symbols = [f"{symbol}.{CONTRACTS[symbol].exchange}" for symbol in symbols]

    engine = BacktestingEngine()
    engine.output = lambda msg: None
    engine.set_parameters(
        vt_symbols=vt_symbols,
        interval=Interval.DAILY,
        start=target_weights.index.min().to_pydatetime(),
        end=target_weights.index.max().to_pydatetime(),
        rates={f"{symbol}.{CONTRACTS[symbol].exchange}": args.commission_rate for symbol in symbols},
        slippages={f"{symbol}.{CONTRACTS[symbol].exchange}": 0.0 for symbol in symbols},
        sizes={f"{symbol}.{CONTRACTS[symbol].exchange}": CONTRACTS[symbol].multiplier for symbol in symbols},
        priceticks={f"{symbol}.{CONTRACTS[symbol].exchange}": CONTRACTS[symbol].tick_size for symbol in symbols},
        capital=args.initial_cash,
        annual_days=252,
    )
    engine.add_strategy(
        TargetWeightReplayStrategy,
        {
            "target_weights_path": str(args.target_weights),
            "equity_curve_path": str(args.akquant_equity),
            "portfolio_value": args.initial_cash,
            "multiplier_by_symbol": {symbol: CONTRACTS[symbol].multiplier for symbol in symbols},
        },
    )
    engine.history_data = load_daily_bars(symbols, args.data_root)
    engine.dts = {key[0] for key in engine.history_data}
    engine.run_backtesting()
    daily = engine.calculate_result()
    stats = engine.calculate_statistics(output=False)
    metrics = normalize_vnpy_statistics(stats)
    akquant_metrics = load_akquant_metrics(args.akquant_metrics)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_root / f"vnpy_portfolio_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    daily.to_csv(output_dir / "daily_results.csv")
    pd.DataFrame([trade.__dict__ for trade in engine.get_all_trades()]).to_csv(output_dir / "trades.csv", index=False)

    comparison_rows = []
    for key in ["total_return_pct", "annualized_return", "max_drawdown_pct", "sharpe_ratio", "trade_count"]:
        comparison_rows.append(
            {
                "metric": key,
                "vnpy_portfolio": metrics.get(key),
                "akquant": akquant_metrics.get(key),
                "diff": metrics.get(key) - float(akquant_metrics.get(key)),
            }
        )
    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(output_dir / "metric_comparison.csv", index=False)
    (output_dir / "metric_comparison.md").write_text(comparison.to_markdown(index=False, floatfmt=".6f") + "\n", encoding="utf-8")

    akquant_equity = load_akquant_equity(args.akquant_equity)
    vnpy_equity = daily[["balance"]].rename(columns={"balance": "vnpy_portfolio"})
    vnpy_equity.index = pd.to_datetime(vnpy_equity.index)
    joined = vnpy_equity.join(akquant_equity.rename(columns={"equity": "akquant"}), how="inner")
    equity_correlation = float(joined["vnpy_portfolio"].corr(joined["akquant"])) if not joined.empty else None
    relative_end_equity_diff = float(joined["vnpy_portfolio"].iloc[-1] / joined["akquant"].iloc[-1] - 1.0) if not joined.empty else None

    summary = {
        "mode": "vnpy_portfoliostrategy_target_weight_replay",
        "portfolio_strategy_source": str(PORTFOLIO_SRC),
        "metrics": metrics,
        "akquant_metrics": akquant_metrics,
        "comparison": comparison_rows,
        "equity_correlation": equity_correlation,
        "relative_end_equity_diff": relative_end_equity_diff,
        "generated_at_utc": timestamp,
        "output_dir": str(output_dir),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"output_dir={output_dir}")
    print((output_dir / "metric_comparison.md").read_text(encoding="utf-8"))
    print(f"equity_correlation={equity_correlation}")
    print(f"relative_end_equity_diff={relative_end_equity_diff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
