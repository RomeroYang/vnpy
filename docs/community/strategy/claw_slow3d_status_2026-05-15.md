# Claw Slow3D vn.py Migration Status 2026-05-15

## Completed

- Cloned vn.py core workspace at `/Users/shawn/github/defintech/vnpy`.
- Cloned `vnpy_portfoliostrategy` source workspace at `/Users/shawn/github/defintech/vnpy_portfoliostrategy`.
- Added a dry-run migration plan under `docs/community/strategy/claw_slow3d_dry_run_plan.md`.
- Added offline deterministic target-weight replay:
  - `examples/claw_slow3d_dry_run/run_parity_backtest.py`
- Added vn.py PortfolioStrategy target-weight replay:
  - `examples/claw_slow3d_dry_run/run_vnpy_portfolio_parity.py`
  - `examples/claw_slow3d_dry_run/strategies/target_weight_replay_strategy.py`
- Added offline CSV reconciliation:
  - `examples/claw_slow3d_dry_run/reconcile_offline_snapshot.py`
  - `config/claw_slow3d/contract_mapping.csv`
  - `config/claw_slow3d/risk_limits.json`
  - `config/claw_slow3d/current_positions.example.csv`

## Parity Result

The accepted parity run is the vn.py PortfolioStrategy replay using the AKQuant equity curve for target contract sizing.

| metric | vn.py PortfolioStrategy | AKQuant | diff |
| --- | ---: | ---: | ---: |
| total_return_pct | `181.7255` | `181.1489` | `+0.5766` |
| max_drawdown_pct | `11.0337` | `11.1745` | `-0.1408` |
| sharpe_ratio | `1.3871` | `1.4445` | `-0.0575` |
| trade_count | `885` | `740` | `+145` |

Additional checks:

- Equity correlation: `0.9988768`
- Relative end-equity difference: `+0.2051%`

Read:

- vn.py bar loading, limit-order crossing, futures multipliers, fee/slippage scale and daily PnL accounting are close enough for migration.
- Trade count differs because vn.py and AKQuant represent close/open and per-symbol order events differently.
- Native vn.py strategy-side dynamic equity sizing remains open. Until that is implemented, dry-run should consume research-generated target contract snapshots rather than recomputing target contracts inside vn.py from static initial capital.

## Offline Dry-Run Result

The offline CSV reconciliation is healthy using the latest claw research snapshot.

| field | value |
| --- | ---: |
| active symbols | `6` |
| gross target weight | `0.90` |
| estimated margin ratio | `0.1117` |
| max abs contract delta | `5` |
| order routing | `false` |

Currently mapped active symbols:

- `CF0 -> CF609.CZCE`
- `HC0 -> hc2610.SHFE`
- `M0 -> m2609.DCE`
- `NR0 -> nr2608.INE`
- `RB0 -> rb2610.SHFE`
- `RU0 -> ru2609.SHFE`

These are placeholder manual mappings and must be checked against actual current main contracts before market-data dry-run.

## Still Required Before CTP Dry-Run

1. Validate manual contract mappings against live exchange volume/open-interest or broker contract list.
2. Replace placeholder `current_positions.example.csv` with a real manually exported position snapshot.
3. Decide account value source for sizing:
   - consume claw-generated target contracts, or
   - implement vn.py-native dynamic equity target sizing.
4. Install and smoke-test CTP-related plugins in an isolated environment.
5. Record vn.py daily bars and compare them against AKShare main-continuous data.
6. Keep `allow_order_routing=false` and do not add any order submission path in the dry-run strategy.
