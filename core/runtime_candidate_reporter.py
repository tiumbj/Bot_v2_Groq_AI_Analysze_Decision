from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from core.candidate_pipeline_postprocessor import CandidatePipelinePostprocessor


def build_runtime_candidate_report(
    scanned_symbols: Iterable[str],
    raw_candidates: Iterable[Dict[str, Any]],
    timeframe: str,
    postprocessor: Optional[CandidatePipelinePostprocessor] = None,
) -> Dict[str, Any]:
    symbols_list: List[str] = [str(x).strip() for x in scanned_symbols if str(x).strip()]
    processor = postprocessor or CandidatePipelinePostprocessor()
    return processor.process(
        candidates=raw_candidates,
        timeframe=str(timeframe).upper().strip(),
        processed_symbols=len(symbols_list),
    )

