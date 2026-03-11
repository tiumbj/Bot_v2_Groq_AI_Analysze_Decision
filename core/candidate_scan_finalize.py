"""
Bot_Pro AI Trading System
File: core/candidate_scan_finalize.py
Version: v1.0.0

Purpose
- Finalize raw candidate scan output into deduped production output
- Convert raw candidate rows into approved/rejected log lines
- Provide one clean integration point for runtime pipeline

Usage
- Collect raw candidates from all scanned symbols first
- Call finalize_candidate_scan(...)
- Print returned log_lines
- Route returned approved rows to AI confirm / execution
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from core.candidate_pipeline_postprocessor import CandidatePipelinePostprocessor
from core.symbol_registry import DEFAULT_SYMBOL_REGISTRY, SymbolRegistry


def finalize_candidate_scan(
    raw_candidates: Iterable[Dict[str, Any]],
    timeframe: str,
    processed_symbols: int,
    symbol_registry: Optional[SymbolRegistry] = None,
) -> Dict[str, Any]:
    """
    Finalize one batch of raw scan results.

    Parameters
    ----------
    raw_candidates:
        Candidate rows collected from all symbols in this scan cycle.
    timeframe:
        Batch timeframe, for example M15.
    processed_symbols:
        Number of symbols scanned in this cycle.

    Returns
    -------
    dict
        {
            "approved": [...],
            "rejected": [...],
            "all_items": [...],
            "log_lines": [...],
            "summary": {...},
        }
    """
    postprocessor = CandidatePipelinePostprocessor(
        symbol_registry=symbol_registry or DEFAULT_SYMBOL_REGISTRY
    )

    return postprocessor.process(
        candidates=list(raw_candidates),
        timeframe=timeframe,
        processed_symbols=processed_symbols,
    )


def format_runtime_console_output(
    raw_candidates: Iterable[Dict[str, Any]],
    timeframe: str,
    processed_symbols: int,
    symbol_registry: Optional[SymbolRegistry] = None,
) -> List[str]:
    """
    Convenience wrapper for runtime console printing.
    """
    result = finalize_candidate_scan(
        raw_candidates=raw_candidates,
        timeframe=timeframe,
        processed_symbols=processed_symbols,
        symbol_registry=symbol_registry,
    )
    return result["log_lines"]