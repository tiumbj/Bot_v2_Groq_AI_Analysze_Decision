from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.schemas import (  # noqa: E402
    AISettings,
    AppSettings,
    ModelSettings,
    RiskSettings,
    SymbolRegistry,
)
from storage.db import DatabaseManager  # noqa: E402


@dataclass(frozen=True)
class RuntimeContext:
    app_settings: AppSettings
    risk_settings: RiskSettings
    ai_settings: AISettings
    model_settings: ModelSettings
    symbol_registry: SymbolRegistry


def load_yaml(file_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        raise FileNotFoundError(f"Missing config file: {file_path}")
    with file_path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file)
    if not isinstance(content, dict):
        raise ValueError(f"Config file must contain a YAML object: {file_path}")
    return content


def build_runtime_context() -> RuntimeContext:
    config_dir = PROJECT_ROOT / "config"

    app_settings = AppSettings.model_validate(load_yaml(config_dir / "settings.yaml"))
    risk_settings = RiskSettings.model_validate(load_yaml(config_dir / "risk.yaml"))
    ai_settings = AISettings.model_validate(load_yaml(config_dir / "ai.yaml"))
    model_settings = ModelSettings.model_validate(load_yaml(config_dir / "model.yaml"))
    symbol_registry = SymbolRegistry.model_validate(load_yaml(config_dir / "symbol.yaml"))

    configured_symbols = set(app_settings.symbols)
    registered_symbols = set(symbol_registry.symbols.keys())

    missing_symbols = sorted(configured_symbols - registered_symbols)
    if missing_symbols:
        raise ValueError(
            "Missing symbol contract(s) in symbol.yaml: " + ", ".join(missing_symbols)
        )

    return RuntimeContext(
        app_settings=app_settings,
        risk_settings=risk_settings,
        ai_settings=ai_settings,
        model_settings=model_settings,
        symbol_registry=symbol_registry,
    )


def initialize_storage(runtime: RuntimeContext) -> None:
    db_path = PROJECT_ROOT / runtime.app_settings.sqlite_path
    db_manager = DatabaseManager(str(db_path))
    db_manager.initialize()

    log_dir = PROJECT_ROOT / runtime.app_settings.log_directory
    log_dir.mkdir(parents=True, exist_ok=True)


def print_runtime_summary(runtime: RuntimeContext) -> None:
    summary = {
        "app_name": runtime.app_settings.app_name,
        "environment": runtime.app_settings.environment.value,
        "symbols": runtime.app_settings.symbols,
        "timeframe": runtime.app_settings.timeframe,
        "dry_run": runtime.app_settings.dry_run,
        "database": runtime.app_settings.sqlite_path,
        "meta_model_enabled": runtime.model_settings.meta_model_enabled,
        "ai_model": runtime.ai_settings.model_name,
        "risk_per_trade_pct": runtime.risk_settings.risk_per_trade_pct,
        "minimum_rr": runtime.risk_settings.minimum_rr,
        "registered_symbol_contracts": sorted(runtime.symbol_registry.symbols.keys()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> int:
    try:
        runtime = build_runtime_context()
        initialize_storage(runtime)
        print_runtime_summary(runtime)
        print("Foundation layer initialized successfully.")
        return 0
    except Exception as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())