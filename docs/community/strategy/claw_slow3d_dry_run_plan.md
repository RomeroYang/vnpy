# Claw Slow3D Commodity Futures Dry-Run Plan

## Boundary

`claw-strategy-lab` remains the research repository:

- AKShare daily main-continuous data download.
- slow3d signal and target-weight generation.
- AKQuant research backtests.
- Parameter scan, subset robustness, rolling robustness.
- Read-only signal snapshot exports.

This vn.py workspace is for the domestic commodity futures dry-run adapter:

- CTP/CTP test connectivity.
- Contract metadata and live market data subscription.
- Account, position, order and trade event observation.
- Main-continuous symbol to tradable contract mapping.
- Portfolio dry-run reconciliation.
- Front-end risk checks before any future paper/live order path is considered.

No order-routing implementation should be added in the first dry-run stage.

## Relevant vn.py Modules

The core `vnpy` repository is the platform base. The commodity dry-run requires the plugin ecosystem:

- `vnpy_ctp`: CTP gateway for domestic futures and options.
- `vnpy_ctptest`: CTP test gateway where available.
- `vnpy_portfoliostrategy`: multi-contract portfolio strategy engine. This is the closest fit for slow3d.
- `vnpy_riskmanager`: front-end risk rules such as order flow, order size, active order count and cancel limits.
- `vnpy_datamanager` or DataRecorder workflow: local bar/tick recording for signal validation.

The README links these as separate application/gateway repositories, so the dry-run implementation should not assume they are present in this core checkout.

## Current Research Candidate

Research source:

- Repository: `/Users/shawn/github/defintech/claw-strategy-lab`
- Strategy: commodity slow3d daily-level long-only trend sleeve.
- Promoted run: `coarse_0036`
- Universe: 39 AKShare main-continuous commodity contracts.

Promoted parameters:

| parameter | value |
| --- | ---: |
| `signal_timeframe` | `3d` |
| `target_annual_vol` | `0.16` |
| `max_symbol_weight` | `0.15` |
| `max_gross_leverage` | `1.0` |
| `regime_strength_threshold` | `0.002` |
| `breakout_lookback` | `12` |
| `atr_ratio` | `0.85` |
| `close_location` | `0.52` |

Research gates already passed:

- Full broad basket annualized return around `21.29%`, max drawdown around `11.17%`.
- Excluding `LC0` annualized return around `19.80%`, max drawdown around `11.32%`.
- Excluding top three trade-level contributors annualized return around `19.99%`, max drawdown around `11.37%`.
- Rolling two-year windows have positive annualized returns in the current sample.
- Current read-only signal dry-run health is `healthy`.

## Dry-Run Definition

Dry-run means:

- Connect to a market data and/or account observation environment.
- Subscribe to mapped tradable commodity contracts.
- Build daily bars from real market data or vn.py local database.
- Generate target positions from the slow3d model.
- Read current account and positions if a gateway is connected.
- Produce target/current/delta reports.
- Run risk checks.
- Log every decision and every skipped action.

Dry-run explicitly does not mean:

- Sending orders.
- Simulated order routing inside the live gateway process.
- Auto paper trading.
- Modifying account positions.
- Relying on a strategy setting alone as the only safety control.

## Architecture

```text
claw-strategy-lab
  export target weights or reusable slow3d signal function
  validate research metrics and dry-run snapshot health

vn.py dry-run workspace
  load CTP contracts and account state
  map main-continuous symbols to tradable contracts
  subscribe/record bars
  run PortfolioStrategy adapter in dry_run mode
  reconcile target positions against observed positions
  write reports and health state
```

The first implementation can import `claw_strategy_lab` in editable mode, or consume exported CSV snapshots. Prefer CSV first for lower coupling:

- `recent_target_weights.csv`
- `signal_snapshot.csv`
- `signal_diff.csv`
- `summary.json`

After dry-run mechanics are stable, add a direct Python adapter.

## Required Files

Create these files in this vn.py workspace or a thin companion package:

```text
config/claw_slow3d/contract_mapping.csv
config/claw_slow3d/risk_limits.yaml
config/claw_slow3d/dry_run_settings.json
examples/claw_slow3d_dry_run/run_no_ui.py
examples/claw_slow3d_dry_run/strategies/claw_slow3d_portfolio_dry_run.py
examples/claw_slow3d_dry_run/reconcile.py
```

Keep CTP credentials out of git. Use vn.py's standard connection JSON under the local `.vntrader` directory or environment-specific local files.

## Contract Mapping

The research uses AKShare main-continuous symbols such as `RB0`, `HC0`, `CF0`.

The dry-run must map each research symbol to a real tradable vt_symbol:

```csv
research_symbol,exchange,vt_symbol,product,roll_rule,roll_date,active
RB0,SHFE,rb2610.SHFE,rebar,manual,,true
HC0,SHFE,hc2610.SHFE,hot_rolled_coil,manual,,true
CF0,CZCE,CF609.CZCE,cotton,manual,,true
```

Initial stage uses manual mapping only. Automated main-contract selection is a later stage and must be validated against exchange volume/open-interest data before use.

## Risk Limits

Initial risk file:

```yaml
dry_run: true
allow_order_routing: false
max_gross_target_weight: 1.0
max_estimated_margin_ratio: 0.35
max_single_symbol_weight: 0.15
max_active_symbols: 12
max_contract_delta_per_symbol: 5
blocked_symbols: []
require_all_contracts_mapped: true
require_recent_daily_bar: true
max_data_lag_days: 3
```

Risk checks should fail closed. If any required mapping, contract, price, margin ratio or account value is missing, write an unhealthy report and do nothing.

## PortfolioStrategy Adapter

Use `vnpy_portfoliostrategy` rather than single-symbol CTA:

- slow3d is a multi-contract portfolio strategy.
- The research risk budget is portfolio-level.
- Target gross exposure and per-symbol caps must be checked across all mapped contracts.

Adapter responsibilities:

1. Load `contract_mapping.csv`.
2. Subscribe to every active `vt_symbol`.
3. Build or load daily bars.
4. Load latest research target weights or compute them from local bars.
5. Convert target weights to target contracts using contract size and latest price.
6. Read observed positions from `MainEngine`/PortfolioStrategy state.
7. Write:
   - `target_positions.csv`
   - `current_positions.csv`
   - `position_delta.csv`
   - `risk_check.json`
   - `dry_run.log`
8. In `dry_run=True`, never call order-sending methods.

Add a second safety layer:

- Do not register any method that transforms deltas into orders in stage 1.
- Keep `vnpy_riskmanager` configured restrictively even though no orders should be sent.

## Validation Stages

### Stage 0: Environment

- Install vn.py core and required plugins.
- Confirm `examples/no_ui/run.py` can initialize.
- Confirm CTP test gateway imports.
- Confirm local database settings.

Exit gate:

- vn.py starts without UI.
- Gateway can be added.
- No credentials committed.

### Stage 1: Offline CSV Dry-Run

- Do not connect CTP.
- Consume `claw-strategy-lab` signal snapshot CSVs.
- Load manual `contract_mapping.csv`.
- Produce target contract report.

Exit gate:

- Every active research symbol maps to exactly one vt_symbol.
- Target contract counts match the research snapshot.
- Risk check is healthy.

Current result:

- Script: `examples/claw_slow3d_dry_run/reconcile_offline_snapshot.py`
- Config:
  - `config/claw_slow3d/contract_mapping.csv`
  - `config/claw_slow3d/risk_limits.json`
  - `config/claw_slow3d/current_positions.example.csv`
- Latest status: `healthy`
- Active symbols: `6`
- Gross target weight: `0.90`
- Estimated margin ratio: about `0.1117`
- Order routing: disabled by design.

### Stage 1.5: vn.py Backtest Parity

Before connecting any live or simulated gateway, run historical parity checks in this vn.py workspace.

Two passes are required:

1. Target-weight replay parity
   - Read `target_weights.csv` generated by `claw-strategy-lab`.
   - Use the same AKShare daily OHLC data.
   - Convert weights to futures contract counts with the same multipliers.
   - Trade on the next daily open and mark to daily close.
   - Compare equity, annualized return, drawdown, Sharpe and trade count against the AKQuant report.
2. PortfolioStrategy engine parity
   - Reimplement the target-weight replay as a `vnpy_portfoliostrategy` backtest.
   - Use vn.py's BacktestingEngine, `BarData`, rates, slippages, sizes and priceticks.
   - Compare the engine result against AKQuant and the deterministic replay.

Current target-weight replay result:

- Script: `examples/claw_slow3d_dry_run/run_parity_backtest.py`
- State: `research/claw_slow3d_vnpy_parity_state.json`
- Latest status: `vnpy_portfolio_parity_passed_with_external_equity_sizing`
- Equity correlation versus AKQuant: about `0.9962`
- End-equity difference versus AKQuant: about `+28.21%`

Interpretation:

- The offline replay is directionally aligned with AKQuant.
- The deterministic replay is useful for debugging target timing but is not the acceptance engine.
- A real `vnpy_portfoliostrategy` BacktestingEngine target replay has now passed the main parity gate when target contract sizing uses the AKQuant equity curve.

Current vn.py PortfolioStrategy parity result:

- Script: `examples/claw_slow3d_dry_run/run_vnpy_portfolio_parity.py`
- Strategy: `examples/claw_slow3d_dry_run/strategies/target_weight_replay_strategy.py`
- Source plugin checkout: `/Users/shawn/github/defintech/vnpy_portfoliostrategy`
- Equity correlation versus AKQuant: about `0.9989`
- End-equity difference versus AKQuant: about `+0.21%`
- Total return: `181.73%` versus AKQuant `181.15%`
- Max drawdown: `11.03%` versus AKQuant `11.17%`
- Sharpe: `1.39` versus AKQuant `1.44`

Interpretation:

- vn.py bar loading, PortfolioStrategy limit-order crossing, futures multipliers, fee/slippage scale and daily PnL accounting are close enough for dry-run migration.
- The remaining unresolved item is native strategy-side equity sizing. The current passing parity run uses AKQuant equity as the sizing base to prove execution parity.
- Trade count differs because vn.py splits close/open and per-symbol events differently from AKQuant.
- Before live-data dry-run, either implement vn.py-native equity sizing or continue consuming research-generated target contract snapshots.

Parity acceptance gates:

- Equity correlation versus AKQuant `>= 0.995`.
- End-equity difference within `5%`.
- Annualized return difference within `3` percentage points.
- Maximum drawdown difference within `2` percentage points.
- Trade count difference explained by deterministic rounding or fill-policy differences.

### Stage 2: Market Data Dry-Run

- Connect CTP market data only where possible.
- Subscribe mapped contracts.
- Record bars locally.
- Compare vn.py daily bars with AKShare main-continuous data.

Exit gate:

- Latest bars are fresh.
- Close prices are within a documented tolerance.
- Signal target changes are explainable.

### Stage 3: Account Observation Dry-Run

- Connect gateway with account/position query enabled.
- Still no order routing from strategy.
- Reconcile observed positions to target positions.

Exit gate:

- Account equity and positions are captured.
- `position_delta.csv` is correct.
- Risk checks remain healthy.
- Manual review can understand every suggested delta.

### Stage 4: Paper/Live Design Review

Only after stage 3 has stable logs:

- Decide whether to add simulated order previews.
- Decide whether vn.py RiskManager settings are sufficient.
- Decide whether paper trading belongs in vn.py or should remain outside this repo.

## Open Questions

- Which CTP environment will be used first: SimNow, OpenCTP, or a broker test account?
- Should dry-run use official settlement close, last daily close, or custom session close?
- Should main-contract mapping be manually approved daily or generated from volume/open interest?
- How should night-session daily bars be assigned to trading dates?
- Should target positions be rounded to nearest contract or floor risk exposure by default?
- What is the account value source during stage 1: fixed notional or observed account equity?

## Immediate Next Actions

1. Install required vn.py plugins in a local virtual environment.
2. Create `config/claw_slow3d/contract_mapping.csv` with the six currently active symbols from the latest research snapshot:
   - `CF0`
   - `HC0`
   - `M0`
   - `NR0`
   - `RB0`
   - `RU0`
3. Implement offline CSV dry-run reconciliation first.
4. Add a no-UI runner after offline reconciliation is deterministic.
5. Connect CTP test market data only after no-order dry-run reports are stable.
