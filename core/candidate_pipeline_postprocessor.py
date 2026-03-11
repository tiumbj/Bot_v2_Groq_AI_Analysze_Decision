"""
Bot_Pro AI Trading System
File: core/candidate_pipeline_postprocessor.py
Version: v1.1.0

Purpose
- Integrate decision validation into the candidate pipeline
- Keep only one approved candidate per underlying setup
- Generate production-safe structured log lines
- Preserve raw symbol casing for runtime logs and downstream execution
- Prepare clean output for downstream AI confirm / execution layers

Design notes
- Analysis layer works on canonical symbols
- Duplicate alias setups must be rejected before confirm/execution
- Execution symbol mapping is intentionally left to the execution layer
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from core.decision_validator import DecisionValidator
from core.symbol_registry import DEFAULT_SYMBOL_REGISTRY, SymbolRegistry


@dataclass
class PipelineProcessResult:
    accepted: List[Dict[str, Any]]
    rejected: List[Dict[str, Any]]
    all_items: List[Dict[str, Any]]
    log_lines: List[str]
    summary: Dict[str, Any]


class CandidatePipelinePostprocessor:
    """
    Post-process candidate rows after detection/state-guard and before AI confirm.

    Input
    - iterable of raw candidate dicts

    Output
    - accepted candidates only
    - rejected duplicate candidates
    - structured log lines
    - summary counters for smoke tests / production logs
    """

    def __init__(
        self,
        symbol_registry: Optional[SymbolRegistry] = None,
        decision_validator: Optional[DecisionValidator] = None,
    ) -> None:
        self.symbol_registry = symbol_registry or DEFAULT_SYMBOL_REGISTRY
        self.decision_validator = decision_validator or DecisionValidator(
            symbol_registry=self.symbol_registry
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process(
        self,
        candidates: Iterable[Dict[str, Any]],
        timeframe: str = "",
        processed_symbols: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Main pipeline entry.

        Parameters
        - candidates: raw candidate rows
        - timeframe: optional batch timeframe for summary log
        - processed_symbols: optional number of symbols scanned in the pipeline

        Returns dict with:
        - accepted
        - rejected
        - all_items
        - log_lines
        - summary
        """
        raw_items = list(candidates)
        validated = self.decision_validator.validate_batch(raw_items)

        accepted = [self._decorate_accepted(x) for x in validated["approved"]]
        rejected = [self._decorate_rejected(x) for x in validated["rejected"]]
        all_items = accepted + rejected

        log_lines: List[str] = []
        for item in accepted:
            log_lines.append(self._format_accept_line(item))

        for item in rejected:
            log_lines.append(self._format_reject_line(item))

        summary = self._build_summary(
            validated_summary=validated["summary"],
            timeframe=timeframe,
            processed_symbols=processed_symbols,
        )
        log_lines.append(self._format_summary_line(summary))

        payload = PipelineProcessResult(
            accepted=accepted,
            rejected=rejected,
            all_items=all_items,
            log_lines=log_lines,
            summary=summary,
        )
        return {
            "accepted": payload.accepted,
            "rejected": payload.rejected,
            "all_items": payload.all_items,
            "log_lines": payload.log_lines,
            "summary": payload.summary,
        }

    # ------------------------------------------------------------------
    # Decoration
    # ------------------------------------------------------------------
    def _decorate_accepted(self, item: Dict[str, Any]) -> Dict[str, Any]:
        decorated = dict(item)
        decorated["analysis_symbol"] = item["canonical_symbol"]
        decorated["underlying_group"] = item["canonical_symbol"]
        decorated["duplicate_blocked"] = False
        decorated["display_symbol"] = item["input_symbol_raw"]
        decorated["runtime_symbol"] = item["execution_symbol"]
        return decorated

    def _decorate_rejected(self, item: Dict[str, Any]) -> Dict[str, Any]:
        decorated = dict(item)
        decorated["analysis_symbol"] = item["canonical_symbol"]
        decorated["underlying_group"] = item["canonical_symbol"]
        decorated["duplicate_blocked"] = item["status"] == "rejected_duplicate"
        decorated["display_symbol"] = item["input_symbol_raw"]
        decorated["runtime_symbol"] = item["execution_symbol"]
        return decorated

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def _build_summary(
        self,
        validated_summary: Dict[str, Any],
        timeframe: str,
        processed_symbols: Optional[int],
    ) -> Dict[str, Any]:
        return {
            "processed": int(processed_symbols or 0),
            "input_candidates": int(validated_summary["input_candidates"]),
            "approved": int(validated_summary["approved_candidates"]),
            "rejected": int(validated_summary["rejected_candidates"]),
            "duplicates_blocked": int(validated_summary["duplicate_rejections"]),
            "unique_underlying_setups": int(validated_summary["unique_underlying_setups"]),
            "timeframe": str(timeframe).upper().strip(),
        }

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _format_accept_line(self, item: Dict[str, Any]) -> str:
        guard = self._safe_text(item.get("guard", ""))
        line = (
            f"[{item['input_symbol_raw']}] "
            f"APPROVED={item['decision']} "
            f"SCORE={self._format_score(item.get('score'))} "
            f"ENTRY={self._format_price(item.get('entry'))} "
            f"SL={self._format_price(item.get('sl'))} "
            f"TP={self._format_price(item.get('tp'))} "
            f"CANONICAL={item['canonical_symbol']} "
            f"SETUP={item['setup_key']}"
        )
        if guard:
            line += f" GUARD={guard}"
        return line

    def _format_reject_line(self, item: Dict[str, Any]) -> str:
        line = (
            f"[{item['input_symbol_raw']}] "
            f"REJECTED={item['status']} "
            f"REASON={item['reason']} "
            f"CANONICAL={item['canonical_symbol']} "
            f"SETUP={item['setup_key']}"
        )
        duplicate_of = self._safe_text(item.get("duplicate_of", ""))
        if duplicate_of:
            line += f" DUPLICATE_OF={duplicate_of}"
        return line

    def _format_summary_line(self, summary: Dict[str, Any]) -> str:
        timeframe = summary["timeframe"] or "NA"
        return (
            f"SUMMARY processed={summary['processed']} "
            f"input_candidates={summary['input_candidates']} "
            f"approved={summary['approved']} "
            f"rejected={summary['rejected']} "
            f"duplicates_blocked={summary['duplicates_blocked']} "
            f"unique_underlying_setups={summary['unique_underlying_setups']} "
            f"timeframe={timeframe}"
        )

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _format_score(value: Any) -> str:
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return "0.00"

    @staticmethod
    def _format_price(value: Any) -> str:
        try:
            return f"{float(value):.2f}"
        except (TypeError, ValueError):
            return "0.00"

    @staticmethod
    def _safe_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()