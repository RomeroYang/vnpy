#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_ROOT = REPO_ROOT / "config" / "claw_slow3d"
DEFAULT_REPORT_ROOT = Path("/Users/shawn/github/defintech/claw-strategy-lab/reports/commodity_slow3d_readonly_dry_run")
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "research" / "claw_slow3d_offline_dry_run"


def latest_snapshot_path(report_root: Path) -> Path:
    dirs = [path for path in report_root.iterdir() if path.is_dir()]
    if not dirs:
        raise FileNotFoundError(f"No dry-run snapshot directories found: {report_root}")
    return max(dirs, key=lambda path: path.name) / "signal_snapshot.csv"


def load_risk_limits(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline vn.py dry-run reconciliation for claw slow3d target snapshot.")
    parser.add_argument("--snapshot", type=Path, default=None)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--contract-mapping", type=Path, default=DEFAULT_CONFIG_ROOT / "contract_mapping.csv")
    parser.add_argument("--risk-limits", type=Path, default=DEFAULT_CONFIG_ROOT / "risk_limits.json")
    parser.add_argument("--current-positions", type=Path, default=DEFAULT_CONFIG_ROOT / "current_positions.example.csv")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    snapshot_path = args.snapshot or latest_snapshot_path(args.report_root)
    snapshot = pd.read_csv(snapshot_path)
    mapping = pd.read_csv(args.contract_mapping)
    risk_limits = load_risk_limits(args.risk_limits)
    current = pd.read_csv(args.current_positions)

    active_mapping = mapping[mapping["active"].astype(str).str.lower().isin(["true", "1", "yes"])].copy()
    merged = snapshot.merge(active_mapping, left_on="symbol", right_on="research_symbol", how="left")
    merged = merged.merge(current, on="vt_symbol", how="left")
    merged["current_contracts"] = pd.to_numeric(merged["current_contracts"], errors="coerce").fillna(0).astype(int)
    merged["target_contracts"] = pd.to_numeric(merged["target_contracts"], errors="coerce").fillna(0).astype(int)
    merged["delta_contracts"] = merged["target_contracts"] - merged["current_contracts"]
    merged["abs_delta_contracts"] = merged["delta_contracts"].abs()
    merged["action"] = merged["delta_contracts"].map(lambda value: "increase" if value > 0 else ("decrease" if value < 0 else "hold"))

    failures: list[str] = []
    warnings: list[str] = []

    if not bool(risk_limits.get("dry_run")):
        failures.append("risk_limits.dry_run must be true")
    if bool(risk_limits.get("allow_order_routing")):
        failures.append("risk_limits.allow_order_routing must be false")

    missing_mapping = merged[merged["vt_symbol"].isna()]["symbol"].tolist()
    if missing_mapping and risk_limits.get("require_all_contracts_mapped", True):
        failures.append(f"missing contract mappings: {missing_mapping}")

    blocked = set(risk_limits.get("blocked_symbols", []))
    blocked_hits = sorted(set(merged["symbol"]) & blocked)
    if blocked_hits:
        failures.append(f"blocked symbols active: {blocked_hits}")

    gross_weight = float(merged["target_weight"].abs().sum())
    if gross_weight > float(risk_limits["max_gross_target_weight"]):
        failures.append(f"gross target weight too high: {gross_weight:.4f}")

    max_weight = float(merged["target_weight"].abs().max()) if not merged.empty else 0.0
    if max_weight > float(risk_limits["max_single_symbol_weight"]):
        failures.append(f"single symbol weight too high: {max_weight:.4f}")

    if len(merged) > int(risk_limits["max_active_symbols"]):
        failures.append(f"too many active symbols: {len(merged)}")

    max_delta = int(merged["abs_delta_contracts"].max()) if not merged.empty else 0
    if max_delta > int(risk_limits["max_contract_delta_per_symbol"]):
        warnings.append(f"contract delta above review threshold: {max_delta}")

    estimated_margin = float(merged["estimated_margin"].sum())
    target_notional = float(merged["target_notional"].abs().sum())
    portfolio_value = target_notional / gross_weight if gross_weight else 0.0
    margin_ratio = estimated_margin / portfolio_value if portfolio_value else 0.0
    if margin_ratio > float(risk_limits["max_estimated_margin_ratio"]):
        failures.append(f"estimated margin ratio too high: {margin_ratio:.4f}")

    generated_at = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_root / generated_at
    output_dir.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_dir / "position_delta.csv", index=False)

    target_positions = merged[
        [
            "symbol",
            "vt_symbol",
            "exchange",
            "signal_date",
            "target_weight",
            "target_contracts",
            "target_notional",
            "estimated_margin",
        ]
    ].copy()
    target_positions.to_csv(output_dir / "target_positions.csv", index=False)
    current.to_csv(output_dir / "current_positions.csv", index=False)

    risk_check = {
        "status": "healthy" if not failures else "unhealthy",
        "failures": failures,
        "warnings": warnings,
        "snapshot_path": str(snapshot_path),
        "contract_mapping": str(args.contract_mapping),
        "current_positions": str(args.current_positions),
        "gross_target_weight": gross_weight,
        "max_single_symbol_weight": max_weight,
        "active_symbol_count": int(len(merged)),
        "max_abs_delta_contracts": max_delta,
        "estimated_margin": estimated_margin,
        "estimated_margin_ratio": margin_ratio,
        "allow_order_routing": False,
        "generated_at_utc": generated_at,
        "output_dir": str(output_dir),
    }
    (output_dir / "risk_check.json").write_text(json.dumps(risk_check, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(risk_check, indent=2, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
