#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_CLAW_ROOT = Path("/Users/shawn/github/defintech/claw-strategy-lab")
DEFAULT_AKQUANT_REPORT = DEFAULT_CLAW_ROOT / "reports" / "akquant_commodity_slow3d" / "coarse_0036_promoted_20260514"
DEFAULT_DATA_ROOT = DEFAULT_CLAW_ROOT / "data" / "akshare_commodity_daily"
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "research" / "claw_slow3d_vnpy_parity"


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    exchange: str
    multiplier: float
    margin_ratio: float
    tick_size: float


CONTRACTS: dict[str, ContractSpec] = {
    "RB0": ContractSpec("RB0", "SHFE", 10.0, 0.13, 1.0),
    "AU0": ContractSpec("AU0", "SHFE", 1000.0, 0.12, 0.02),
    "AG0": ContractSpec("AG0", "SHFE", 15.0, 0.12, 1.0),
    "CU0": ContractSpec("CU0", "SHFE", 5.0, 0.12, 10.0),
    "I0": ContractSpec("I0", "DCE", 100.0, 0.15, 0.5),
    "M0": ContractSpec("M0", "DCE", 10.0, 0.10, 1.0),
    "P0": ContractSpec("P0", "DCE", 10.0, 0.12, 2.0),
    "SR0": ContractSpec("SR0", "CZCE", 10.0, 0.10, 1.0),
    "CF0": ContractSpec("CF0", "CZCE", 5.0, 0.10, 5.0),
    "SC0": ContractSpec("SC0", "INE", 1000.0, 0.15, 0.1),
    "HC0": ContractSpec("HC0", "SHFE", 10.0, 0.13, 1.0),
    "AL0": ContractSpec("AL0", "SHFE", 5.0, 0.12, 5.0),
    "ZN0": ContractSpec("ZN0", "SHFE", 5.0, 0.12, 5.0),
    "NI0": ContractSpec("NI0", "SHFE", 1.0, 0.19, 10.0),
    "SN0": ContractSpec("SN0", "SHFE", 1.0, 0.16, 10.0),
    "RU0": ContractSpec("RU0", "SHFE", 10.0, 0.12, 5.0),
    "FU0": ContractSpec("FU0", "SHFE", 10.0, 0.15, 1.0),
    "BU0": ContractSpec("BU0", "SHFE", 10.0, 0.15, 1.0),
    "SP0": ContractSpec("SP0", "SHFE", 10.0, 0.12, 2.0),
    "NR0": ContractSpec("NR0", "INE", 10.0, 0.12, 5.0),
    "LU0": ContractSpec("LU0", "INE", 10.0, 0.15, 1.0),
    "Y0": ContractSpec("Y0", "DCE", 10.0, 0.10, 2.0),
    "C0": ContractSpec("C0", "DCE", 10.0, 0.10, 1.0),
    "A0": ContractSpec("A0", "DCE", 10.0, 0.12, 1.0),
    "J0": ContractSpec("J0", "DCE", 100.0, 0.20, 0.5),
    "JM0": ContractSpec("JM0", "DCE", 60.0, 0.20, 0.5),
    "EG0": ContractSpec("EG0", "DCE", 10.0, 0.12, 1.0),
    "EB0": ContractSpec("EB0", "DCE", 5.0, 0.12, 1.0),
    "PG0": ContractSpec("PG0", "DCE", 20.0, 0.12, 1.0),
    "TA0": ContractSpec("TA0", "CZCE", 5.0, 0.10, 2.0),
    "OI0": ContractSpec("OI0", "CZCE", 10.0, 0.10, 1.0),
    "RM0": ContractSpec("RM0", "CZCE", 10.0, 0.10, 1.0),
    "MA0": ContractSpec("MA0", "CZCE", 10.0, 0.12, 1.0),
    "FG0": ContractSpec("FG0", "CZCE", 20.0, 0.12, 1.0),
    "SA0": ContractSpec("SA0", "CZCE", 20.0, 0.12, 1.0),
    "UR0": ContractSpec("UR0", "CZCE", 20.0, 0.10, 1.0),
    "PF0": ContractSpec("PF0", "CZCE", 5.0, 0.10, 2.0),
    "SI0": ContractSpec("SI0", "GFEX", 5.0, 0.12, 5.0),
    "LC0": ContractSpec("LC0", "GFEX", 1.0, 0.12, 50.0),
}


def load_price_frames(symbols: list[str], data_root: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        path = data_root / f"{symbol}-1d.csv"
        frame = pd.read_csv(path, parse_dates=["datetime"])
        frame = frame.sort_values("datetime").drop_duplicates("datetime").set_index("datetime")
        for column in ["open", "high", "low", "close", "volume"]:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frames[symbol] = frame.dropna(subset=["open", "high", "low", "close"])
    return frames


def load_target_weights(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["datetime"]).set_index("datetime")
    return frame.sort_index().astype(float)


def load_akquant_metrics(path: Path) -> dict[str, Any]:
    frame = pd.read_csv(path, index_col=0)
    values = frame["value"].to_dict()
    parsed: dict[str, Any] = {}
    for key, raw in values.items():
        try:
            parsed[key] = float(raw)
        except (TypeError, ValueError):
            parsed[key] = raw
    return parsed


def load_akquant_equity(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["timestamp"])
    frame["datetime"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
    return frame[["datetime", "equity"]].set_index("datetime").sort_index()


def annualized_return(total_return: float, start: pd.Timestamp, end: pd.Timestamp) -> float:
    years = max((end - start).days / 365.25, 1e-9)
    return (1.0 + total_return) ** (1.0 / years) - 1.0


def max_drawdown_pct(equity: pd.Series) -> float:
    drawdown = equity / equity.cummax() - 1.0
    return abs(float(drawdown.min() * 100.0))


def sharpe_ratio(equity: pd.Series) -> float:
    returns = equity.pct_change().dropna()
    if returns.empty:
        return 0.0
    std = returns.std(ddof=0)
    if std == 0 or np.isnan(std):
        return 0.0
    return float(returns.mean() / std * np.sqrt(252))


def run_target_replay(
    *,
    target_weights: pd.DataFrame,
    prices: dict[str, pd.DataFrame],
    initial_cash: float,
    commission_rate: float,
    slippage_bps: float,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, float]]:
    symbols = list(target_weights.columns)
    dates = target_weights.index
    cash = float(initial_cash)
    positions = {symbol: 0 for symbol in symbols}
    previous_closes: dict[str, float] = {}
    equity_rows: list[dict[str, Any]] = []
    position_rows: list[dict[str, Any]] = []
    turnover = 0.0
    total_commission = 0.0
    trade_count = 0
    pending_targets: dict[str, int] | None = None

    for date in dates:
        today_frames = {
            symbol: prices[symbol].loc[date]
            for symbol in symbols
            if date in prices[symbol].index
        }
        if not today_frames:
            continue
        opens = {symbol: float(row["open"]) for symbol, row in today_frames.items() if pd.notna(row["open"])}
        closes = {symbol: float(row["close"]) for symbol, row in today_frames.items() if pd.notna(row["close"])}

        # Mark existing positions from previous close to today's open, fill pending targets, then mark to close.
        open_pnl = 0.0
        for symbol, open_price in opens.items():
            old_close = previous_closes.get(symbol)
            if old_close is not None:
                open_pnl += positions[symbol] * (open_price - old_close) * CONTRACTS[symbol].multiplier
        cash += open_pnl

        if pending_targets is not None:
            for symbol, target_position in pending_targets.items():
                if symbol not in opens:
                    continue
                delta = target_position - positions[symbol]
                if delta == 0:
                    continue
                price = opens[symbol]
                spec = CONTRACTS[symbol]
                traded_notional = abs(delta) * price * spec.multiplier
                commission = traded_notional * commission_rate
                slippage = traded_notional * slippage_bps / 10_000.0
                cash -= commission + slippage
                turnover += traded_notional
                total_commission += commission
                trade_count += 1
                positions[symbol] = target_position

        close_pnl = 0.0
        for symbol, close in closes.items():
            if symbol not in opens:
                continue
            close_pnl += positions[symbol] * (close - opens[symbol]) * CONTRACTS[symbol].multiplier
        cash += close_pnl

        portfolio_value = cash
        current_notional = sum(abs(positions[symbol]) * closes[symbol] * CONTRACTS[symbol].multiplier for symbol in closes)
        next_targets: dict[str, int] = {}
        for symbol in closes:
            target_notional = float(target_weights.loc[date, symbol]) * portfolio_value
            next_targets[symbol] = round(target_notional / (closes[symbol] * CONTRACTS[symbol].multiplier))

        pending_targets = next_targets

        margin = 0.0
        market_value = 0.0
        for symbol in closes:
            spec = CONTRACTS[symbol]
            close = closes[symbol]
            pos = positions[symbol]
            symbol_market_value = pos * close * spec.multiplier
            market_value += symbol_market_value
            margin += abs(symbol_market_value) * spec.margin_ratio
            if pos:
                position_rows.append(
                    {
                        "datetime": date,
                        "symbol": symbol,
                        "position": pos,
                        "close": close,
                        "market_value": symbol_market_value,
                        "margin": abs(symbol_market_value) * spec.margin_ratio,
                    }
                )

        equity_rows.append(
            {
                "datetime": date,
                "equity": cash,
                "market_value": market_value,
                "gross_notional": current_notional,
                "margin": margin,
            }
        )
        previous_closes = closes

    equity = pd.DataFrame(equity_rows).set_index("datetime")
    position_frame = pd.DataFrame(position_rows)
    total_return_pct = (float(equity["equity"].iloc[-1]) / initial_cash - 1.0) * 100.0
    metrics = {
        "total_return_pct": total_return_pct,
        "annualized_return": annualized_return(total_return_pct / 100.0, equity.index[0], equity.index[-1]),
        "max_drawdown_pct": max_drawdown_pct(equity["equity"]),
        "sharpe_ratio": sharpe_ratio(equity["equity"]),
        "trade_count": float(trade_count),
        "total_commission": total_commission,
        "turnover": turnover,
        "end_market_value": float(equity["equity"].iloc[-1]),
        "max_margin_ratio": float((equity["margin"] / equity["equity"]).max()),
    }
    return equity, position_frame, metrics


def write_report(
    *,
    output_root: Path,
    equity: pd.DataFrame,
    positions: pd.DataFrame,
    metrics: dict[str, float],
    akquant_metrics: dict[str, Any],
    args: argparse.Namespace,
) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    equity.to_csv(output_dir / "equity_curve.csv")
    positions.to_csv(output_dir / "positions.csv", index=False)

    comparison_rows = []
    for key in ["total_return_pct", "annualized_return", "max_drawdown_pct", "sharpe_ratio", "trade_count"]:
        replay = metrics.get(key)
        akquant = akquant_metrics.get(key)
        if isinstance(akquant, (int, float)) and replay is not None:
            diff = replay - float(akquant)
        else:
            diff = None
        comparison_rows.append({"metric": key, "target_replay": replay, "akquant": akquant, "diff": diff})
    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(output_dir / "metric_comparison.csv", index=False)

    summary = {
        "mode": "target_weight_replay_parity",
        "engine_note": "Offline deterministic target replay in vn.py workspace; PortfolioStrategy plugin parity is the next stage.",
        "args": {key: str(value) for key, value in vars(args).items()},
        "metrics": metrics,
        "akquant_metrics": akquant_metrics,
        "comparison": comparison_rows,
        "generated_at_utc": timestamp,
        "output_dir": str(output_dir),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (output_dir / "metric_comparison.md").write_text(comparison.to_markdown(index=False, floatfmt=".6f") + "\n", encoding="utf-8")
    return output_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay claw slow3d target weights for vn.py migration parity checks.")
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
    target_weights = load_target_weights(args.target_weights)
    symbols = list(target_weights.columns)
    prices = load_price_frames(symbols, args.data_root)
    akquant_metrics = load_akquant_metrics(args.akquant_metrics)
    akquant_equity = load_akquant_equity(args.akquant_equity)
    equity, positions, metrics = run_target_replay(
        target_weights=target_weights,
        prices=prices,
        initial_cash=args.initial_cash,
        commission_rate=args.commission_rate,
        slippage_bps=args.slippage_bps,
    )
    output_dir = write_report(
        output_root=args.output_root,
        equity=equity,
        positions=positions,
        metrics=metrics,
        akquant_metrics=akquant_metrics,
        args=args,
    )
    print(f"output_dir={output_dir}")
    print((output_dir / "metric_comparison.md").read_text(encoding="utf-8"))
    joined = equity[["equity"]].rename(columns={"equity": "target_replay"}).join(
        akquant_equity.rename(columns={"equity": "akquant"}),
        how="inner",
    )
    if not joined.empty:
        corr = joined["target_replay"].corr(joined["akquant"])
        relative_end_diff = joined["target_replay"].iloc[-1] / joined["akquant"].iloc[-1] - 1.0
        print(f"equity_correlation={corr:.6f}")
        print(f"relative_end_equity_diff={relative_end_diff:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
