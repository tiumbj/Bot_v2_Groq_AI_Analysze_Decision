"""
OracleBot-Pro
File: app/smoke_test_candidate.py
Version: v1.1.0

Purpose
- Smoke test candidate pipeline for multi-symbol runtime
- Robust fallback across market_data.py and mt5_gateway.py
- Do not redesign architecture
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.candidate_engine import CandidateEngine
from core.logger_engine import LoggerEngine
from core.state_guard import StateGuard


def load_yaml(file_path: Path) -> Dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def import_project_modules():
    from core import feature_engine as feature_engine_module
    from core import market_data as market_data_module
    from core import mt5_gateway as mt5_gateway_module

    return mt5_gateway_module, market_data_module, feature_engine_module


def pick_first_existing_attr(obj: Any, names: Iterable[str]) -> Optional[Any]:
    for name in names:
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def filter_kwargs_for_callable(func: Callable[..., Any], kwargs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        signature = inspect.signature(func)
    except Exception:
        return kwargs

    accepted: Dict[str, Any] = {}
    for key, value in kwargs.items():
        if key in signature.parameters:
            accepted[key] = value
    return accepted


def try_call(func: Callable[..., Any], attempt_kwargs: List[Dict[str, Any]]) -> Any:
    last_error: Optional[Exception] = None

    for kwargs in attempt_kwargs:
        try:
            filtered = filter_kwargs_for_callable(func, kwargs)
            return func(**filtered)
        except Exception as exc:
            last_error = exc

    try:
        return func()
    except Exception as exc:
        last_error = exc

    raise RuntimeError(f"Call failed: {last_error}")


def instantiate_from_module(module: Any, candidate_names: List[str], **kwargs) -> Any:
    for name in candidate_names:
        cls = getattr(module, name, None)
        if cls is None or not inspect.isclass(cls):
            continue
        try:
            return cls(**filter_kwargs_for_callable(cls, kwargs))
        except Exception:
            try:
                return cls()
            except Exception:
                continue
    return None


def build_gateway(mt5_gateway_module: Any) -> Any:
    gateway = instantiate_from_module(
        mt5_gateway_module,
        ["MT5Gateway", "Mt5Gateway"],
    )

    if gateway is not None:
        init_func = pick_first_existing_attr(gateway, ["initialize", "ensure_connection", "connect"])
        if callable(init_func):
            try:
                init_func()
            except Exception:
                pass
        return gateway

    class ModuleGatewayAdapter:
        def __init__(self, module: Any) -> None:
            self.module = module

        def has_open_position(self, symbol: str) -> bool:
            func = pick_first_existing_attr(
                self.module,
                ["has_open_position", "symbol_has_open_position"],
            )
            if callable(func):
                try:
                    return bool(try_call(func, [{"symbol": symbol}]))
                except Exception:
                    return False
            return False

        def shutdown(self) -> None:
            func = pick_first_existing_attr(self.module, ["shutdown", "close"])
            if callable(func):
                try:
                    func()
                except Exception:
                    pass

    init_func = pick_first_existing_attr(mt5_gateway_module, ["initialize", "ensure_connection", "connect"])
    if callable(init_func):
        try:
            init_func()
        except Exception:
            pass

    return ModuleGatewayAdapter(mt5_gateway_module)


def build_market_loader(market_data_module: Any, gateway: Any) -> Any:
    loader = instantiate_from_module(
        market_data_module,
        ["MarketDataLoader", "MarketDataService", "MarketDataEngine", "MarketData"],
        gateway=gateway,
        mt5_gateway=gateway,
    )
    if loader is not None:
        return loader
    return market_data_module


def build_feature_engine(feature_engine_module: Any) -> Any:
    engine = instantiate_from_module(
        feature_engine_module,
        ["FeatureEngine", "FeatureBuilder"],
    )
    if engine is not None:
        return engine
    return feature_engine_module


def fetch_bars_from_loader(loader: Any, symbol: str, timeframe: str, bars: int) -> Any:
    candidate_method_names = [
        "load_ohlcv",
        "load_bars",
        "fetch_ohlcv",
        "fetch_bars",
        "get_ohlcv",
        "get_bars",
        "load_frame",
        "load_symbol_ohlcv",
        "load_symbol_bars",
        "get_symbol_ohlcv",
        "get_symbol_bars",
        "get_symbol_frame",
        "load_symbol_frame",
        "fetch_symbol_ohlcv",
        "fetch_symbol_bars",
        "load",
    ]

    method = pick_first_existing_attr(loader, candidate_method_names)
    if not callable(method):
        raise RuntimeError("No market data loader method found")

    attempts = [
        {"symbol": symbol, "timeframe": timeframe, "bars": bars},
        {"symbol": symbol, "timeframe": timeframe, "count": bars},
        {"symbol": symbol, "timeframe": timeframe, "limit": bars},
        {"symbol": symbol, "tf": timeframe, "bars": bars},
        {"symbol": symbol, "tf": timeframe, "count": bars},
        {"symbol": symbol, "tf": timeframe, "limit": bars},
        {"symbol": symbol, "bars": bars},
        {"symbol": symbol, "count": bars},
        {"symbol": symbol, "limit": bars},
    ]
    return try_call(method, attempts)


def fetch_bars_from_gateway(gateway: Any, symbol: str, timeframe: str, bars: int) -> Any:
    candidate_method_names = [
        "get_rates",
        "fetch_rates",
        "rates_fetch",
        "copy_rates",
        "copy_rates_from_pos",
        "get_ohlcv",
        "fetch_ohlcv",
        "get_bars",
        "fetch_bars",
    ]

    method = pick_first_existing_attr(gateway, candidate_method_names)
    if not callable(method):
        raise RuntimeError("No MT5 gateway rates method found")

    attempts = [
        {"symbol": symbol, "timeframe": timeframe, "bars": bars},
        {"symbol": symbol, "timeframe": timeframe, "count": bars},
        {"symbol": symbol, "timeframe": timeframe, "limit": bars},
        {"symbol": symbol, "tf": timeframe, "bars": bars},
        {"symbol": symbol, "tf": timeframe, "count": bars},
        {"symbol": symbol, "tf": timeframe, "limit": bars},
        {"symbol": symbol, "bars": bars},
        {"symbol": symbol, "count": bars},
        {"symbol": symbol, "limit": bars},
    ]
    return try_call(method, attempts)


def fetch_bars(loader: Any, gateway: Any, symbol: str, timeframe: str, bars: int = 400) -> Any:
    loader_error: Optional[Exception] = None
    gateway_error: Optional[Exception] = None

    try:
        return fetch_bars_from_loader(loader=loader, symbol=symbol, timeframe=timeframe, bars=bars)
    except Exception as exc:
        loader_error = exc

    try:
        return fetch_bars_from_gateway(gateway=gateway, symbol=symbol, timeframe=timeframe, bars=bars)
    except Exception as exc:
        gateway_error = exc

    raise RuntimeError(
        f"Failed to fetch bars for {symbol} | loader_error={loader_error} | gateway_error={gateway_error}"
    )


def build_snapshot(
    engine: Any,
    symbol: str,
    timeframe: str,
    bars_data: Any,
    spread: float,
    open_position_flag: bool,
) -> Any:
    candidate_method_names = [
        "build_feature_snapshot",
        "build_snapshot",
        "compute_features",
        "create_snapshot",
        "generate_snapshot",
    ]

    method = pick_first_existing_attr(engine, candidate_method_names)
    if not callable(method):
        raise RuntimeError("No feature engine snapshot builder method found")

    attempts = [
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "frame": bars_data,
            "spread": spread,
            "open_position_flag": open_position_flag,
        },
        {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": bars_data,
            "spread": spread,
            "open_position_flag": open_position_flag,
        },
        {
            "symbol": symbol,
            "tf": timeframe,
            "frame": bars_data,
            "spread": spread,
            "open_position_flag": open_position_flag,
        },
        {
            "symbol": symbol,
            "tf": timeframe,
            "bars": bars_data,
            "spread": spread,
            "open_position_flag": open_position_flag,
        },
    ]
    return try_call(method, attempts)


def get_spread(gateway: Any, symbol: str) -> float:
    tick_method = pick_first_existing_attr(gateway, ["get_tick", "tick", "read_tick", "symbol_tick"])
    if callable(tick_method):
        try:
            tick = try_call(tick_method, [{"symbol": symbol}])
            if isinstance(tick, dict):
                bid = float(tick.get("bid", 0.0))
                ask = float(tick.get("ask", 0.0))
                return max(ask - bid, 0.0)
            bid = float(getattr(tick, "bid", 0.0))
            ask = float(getattr(tick, "ask", 0.0))
            return max(ask - bid, 0.0)
        except Exception:
            return 0.0
    return 0.0


def snapshot_bar_time(snapshot: Any) -> Any:
    if isinstance(snapshot, dict):
        return snapshot.get("bar_time") or snapshot.get("time")
    if hasattr(snapshot, "bar_time"):
        return snapshot.bar_time
    if hasattr(snapshot, "time"):
        return snapshot.time
    return "UNKNOWN_BAR_TIME"


def print_result(symbol: str, candidate: Any, guard: Any) -> None:
    if candidate is None:
        print(f"[{symbol}] NO_CANDIDATE")
        return

    print(
        f"[{symbol}] "
        f"CANDIDATE={candidate.direction} "
        f"SCORE={candidate.score:.2f} "
        f"ENTRY={candidate.entry_hint} "
        f"SL={candidate.stop_hint} "
        f"TP={candidate.target_hint} "
        f"GUARD={guard.reason}"
    )


def main() -> int:
    settings = load_yaml(PROJECT_ROOT / "config" / "settings.yaml")
    symbols = settings.get("symbols") or []
    timeframe = str(settings.get("timeframe", "M15")).upper()

    if not symbols:
        raise RuntimeError("No symbols found in config/settings.yaml")

    mt5_gateway_module, market_data_module, feature_engine_module = import_project_modules()

    gateway = build_gateway(mt5_gateway_module)
    loader = build_market_loader(market_data_module, gateway)
    feature_engine = build_feature_engine(feature_engine_module)

    candidate_engine = CandidateEngine()
    state_guard = StateGuard(
        db_path=str(PROJECT_ROOT / "storage" / "bot.db"),
        timeframe=timeframe,
        cooldown_bars=2,
    )
    logger = LoggerEngine(base_dir=str(PROJECT_ROOT / "storage" / "logs"))

    processed_count = 0
    candidate_count = 0

    try:
        for symbol in symbols:
            try:
                has_position = False
                if hasattr(gateway, "has_open_position"):
                    try:
                        has_position = bool(gateway.has_open_position(symbol))
                    except Exception:
                        has_position = False

                spread = get_spread(gateway=gateway, symbol=symbol)
                bars_data = fetch_bars(
                    loader=loader,
                    gateway=gateway,
                    symbol=symbol,
                    timeframe=timeframe,
                    bars=400,
                )

                snapshot = build_snapshot(
                    engine=feature_engine,
                    symbol=symbol,
                    timeframe=timeframe,
                    bars_data=bars_data,
                    spread=spread,
                    open_position_flag=has_position,
                )

                logger.log_feature_snapshot(snapshot)
                candidate = candidate_engine.detect_candidate(snapshot)

                if candidate is None:
                    print_result(symbol=symbol, candidate=None, guard=None)
                    processed_count += 1
                    continue

                guard = state_guard.evaluate(
                    symbol=symbol,
                    bar_time=snapshot_bar_time(snapshot),
                    gateway=gateway,
                )

                logger.log_candidate_event(candidate)
                logger.log_guard_decision(guard)
                state_guard.record_candidate_seen(symbol=symbol, bar_time=candidate.bar_time)

                print_result(symbol=symbol, candidate=candidate, guard=guard)

                processed_count += 1
                candidate_count += 1

            except Exception as exc:
                print(f"[{symbol}] ERROR={exc}")

    finally:
        shutdown_func = pick_first_existing_attr(gateway, ["shutdown", "close"])
        if callable(shutdown_func):
            try:
                shutdown_func()
            except Exception:
                pass

    print(
        f"SUMMARY processed={processed_count} "
        f"candidates={candidate_count} "
        f"timeframe={timeframe} "
        f"symbols={len(symbols)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())