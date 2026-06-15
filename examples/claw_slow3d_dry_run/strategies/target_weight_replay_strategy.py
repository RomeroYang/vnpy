from __future__ import annotations

from pathlib import Path

import pandas as pd

from vnpy.trader.constant import Direction
from vnpy.trader.object import BarData

from vnpy_portfoliostrategy import StrategyTemplate


class TargetWeightReplayStrategy(StrategyTemplate):
    """Replay precomputed slow3d target weights inside vn.py PortfolioStrategy."""

    author = "defintech"

    target_weights_path: str = ""
    equity_curve_path: str = ""
    portfolio_value: float = 1_000_000.0
    multiplier_by_symbol: dict[str, float] = {}

    parameters = [
        "target_weights_path",
        "equity_curve_path",
        "portfolio_value",
        "multiplier_by_symbol",
    ]
    variables = []

    def __init__(self, strategy_engine, strategy_name: str, vt_symbols: list[str], setting: dict) -> None:
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)
        self.target_weights = pd.read_csv(Path(self.target_weights_path), parse_dates=["datetime"]).set_index("datetime")
        self.equity_curve = self.load_equity_curve()
        self.last_portfolio_value = float(self.portfolio_value)

    def load_equity_curve(self) -> pd.Series:
        if not self.equity_curve_path:
            return pd.Series(dtype=float)
        frame = pd.read_csv(Path(self.equity_curve_path), parse_dates=["timestamp"])
        frame["datetime"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
        frame["date"] = frame["datetime"].dt.normalize()
        return frame.drop_duplicates("date").set_index("date")["equity"].astype(float).sort_index()

    def on_init(self) -> None:
        self.write_log("target weight replay initialized")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        if not bars:
            return

        dt = next(iter(bars.values())).datetime.replace(tzinfo=None)
        date_key = pd.Timestamp(dt.date())
        if date_key not in self.target_weights.index:
            return

        total_value = self.current_portfolio_value(date_key)
        for vt_symbol, bar in bars.items():
            research_symbol = vt_symbol.split(".")[0]
            multiplier = float(self.multiplier_by_symbol[research_symbol])
            weight = float(self.target_weights.loc[date_key, research_symbol])
            target = round(weight * total_value / (bar.close_price * multiplier))
            self.set_target(vt_symbol, target)

        self.rebalance_portfolio(bars)
        self.put_event()

    def current_portfolio_value(self, date_key: pd.Timestamp) -> float:
        if not self.equity_curve.empty and date_key in self.equity_curve.index:
            value = float(self.equity_curve.loc[date_key])
            self.last_portfolio_value = value
            return value
        daily_df = getattr(self.strategy_engine, "daily_df", None)
        if daily_df is not None and not daily_df.empty and "balance" in daily_df:
            value = float(daily_df["balance"].iloc[-1])
            self.last_portfolio_value = value
            return value
        daily_results = getattr(self.strategy_engine, "daily_results", {})
        if daily_results:
            net_pnl = sum(float(getattr(result, "net_pnl", 0.0)) for result in daily_results.values())
            value = float(self.portfolio_value) + net_pnl
            self.last_portfolio_value = value
            return value
        return self.last_portfolio_value

    def calculate_price(self, vt_symbol: str, direction: Direction, reference: float) -> float:
        return reference
