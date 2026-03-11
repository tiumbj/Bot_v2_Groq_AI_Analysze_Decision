from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_yaml(file_path: Path) -> Dict[str, Any]:
    if not file_path.exists():
        return {}
    with file_path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle) or {}
    return content if isinstance(content, dict) else {}


def _normalize_symbol(value: str) -> str:
    return str(value).strip().upper()


def _split_base(value: str) -> str:
    text = _normalize_symbol(value)
    if "." in text:
        return text.split(".", 1)[0].strip()
    return text


@dataclass(frozen=True)
class SymbolDescription:
    input_symbol: str
    canonical_symbol: str
    execution_symbol: str
    known_matches: list[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "input_symbol": self.input_symbol,
            "canonical_symbol": self.canonical_symbol,
            "execution_symbol": self.execution_symbol,
            "known_matches": list(self.known_matches),
        }


class SymbolRegistry:
    def __init__(self, known_symbols: Iterable[str]) -> None:
        self.known_symbols = sorted({_normalize_symbol(s) for s in known_symbols if str(s).strip()})

    def normalize_symbol(self, symbol: str) -> str:
        return _normalize_symbol(symbol)

    def to_canonical(self, symbol: str) -> str:
        raw = _split_base(symbol)
        if not raw:
            return ""

        if raw == "GOLD":
            return "XAUUSD"
        if raw == "XAUUSD":
            return "XAUUSD"
        if raw.startswith("XAUUSD") and raw[len("XAUUSD") :].isalpha():
            return "XAUUSD"

        if raw in self.known_symbols:
            return raw

        trimmed = raw
        while trimmed and trimmed[-1].isalpha():
            trimmed = trimmed[:-1]
            if trimmed in self.known_symbols:
                return trimmed

        return raw

    def to_canonical_normalized(self, symbol: str) -> str:
        return _normalize_symbol(self.to_canonical(symbol))

    def map_execution_symbol(self, broker_name: str, symbol: str) -> str:
        raw = _split_base(symbol)
        if raw in self.known_symbols:
            return raw

        canonical = self.to_canonical(raw)
        candidates = self._matches_for_canonical(canonical)
        if not candidates:
            return raw

        broker = str(broker_name).strip().upper()
        if broker == "EXNESS":
            preferred = f"{canonical}M"
            if preferred in candidates:
                return preferred

        if canonical in candidates:
            return canonical

        return sorted(candidates, key=len)[0]

    def describe_symbol(self, symbol: str, broker_name: Optional[str] = None) -> Dict[str, Any]:
        raw = _split_base(symbol)
        canonical = self.to_canonical(raw)
        matches = sorted(self._matches_for_canonical(canonical))
        execution = self.map_execution_symbol(broker_name or "", raw)
        return SymbolDescription(
            input_symbol=raw,
            canonical_symbol=canonical,
            execution_symbol=execution,
            known_matches=matches,
        ).to_dict()

    def _matches_for_canonical(self, canonical: str) -> set[str]:
        if not canonical:
            return set()
        out: set[str] = set()
        for sym in self.known_symbols:
            if sym == canonical:
                out.add(sym)
                continue
            if sym.startswith(canonical) and sym[len(canonical) :].isalpha():
                out.add(sym)
        return out


def _build_default_registry() -> SymbolRegistry:
    config = _load_yaml(_project_root() / "config" / "symbol.yaml")
    symbol_map: Any = config.get("symbols") if isinstance(config, dict) else None
    known = symbol_map.keys() if isinstance(symbol_map, dict) else []
    return SymbolRegistry(known_symbols=known)


DEFAULT_SYMBOL_REGISTRY = _build_default_registry()

SymbolRegistryEngine = SymbolRegistry
