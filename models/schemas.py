from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.enums import (
    BreakoutState,
    Direction,
    Environment,
    ExecutionStatus,
    OrderType,
    SessionType,
    SetupType,
)


class AppSettings(BaseModel):
    app_name: str = Field(..., min_length=1)
    environment: Environment
    timezone: str = Field(..., min_length=1)
    symbols: list[str] = Field(..., min_length=1)
    timeframe: str = Field(..., min_length=1)
    primary_loop_seconds: int = Field(..., ge=1)
    sqlite_path: str = Field(..., min_length=1)
    log_directory: str = Field(..., min_length=1)
    dry_run: bool = False
    max_bars_fetch: int = Field(..., ge=100, le=5000)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: list[str]) -> list[str]:
        cleaned = []
        seen = set()

        for item in value:
            symbol = item.strip()
            if not symbol:
                raise ValueError("symbols must not contain empty entries")
            if symbol in seen:
                raise ValueError(f"duplicate symbol detected: {symbol}")
            seen.add(symbol)
            cleaned.append(symbol)

        if not cleaned:
            raise ValueError("symbols must contain at least one symbol")

        return cleaned


class RiskSettings(BaseModel):
    risk_per_trade_pct: float = Field(..., gt=0.0, le=5.0)
    minimum_rr: float = Field(..., gt=0.0, le=10.0)
    max_open_positions_per_symbol: int = Field(..., ge=1, le=1)
    max_daily_loss_pct: float = Field(..., gt=0.0, le=20.0)
    cooldown_bars: int = Field(..., ge=0, le=100)
    one_trade_per_bar: bool = True
    allow_market_order_only: bool = True
    hard_max_stop_distance_atr: float = Field(..., gt=0.1, le=20.0)
    default_take_profit_rr: float = Field(..., gt=0.1, le=20.0)


class AISettings(BaseModel):
    provider: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    temperature: float = Field(..., ge=0.0, le=1.0)
    timeout_seconds: int = Field(..., ge=1, le=120)
    max_retries: int = Field(..., ge=0, le=10)
    prompt_version: str = Field(..., min_length=1)
    require_json_response: bool = True
    minimum_confidence: float = Field(..., ge=0.0, le=1.0)


class ModelSettings(BaseModel):
    meta_model_enabled: bool
    meta_model_name: str = Field(..., min_length=1)
    keep_probability_threshold: float = Field(..., ge=0.0, le=1.0)
    drift_detector_name: str = Field(..., min_length=1)
    label_name: str = Field(..., min_length=1)


class SymbolContract(BaseModel):
    point_value: float = Field(..., gt=0.0)
    price_digits: int = Field(..., ge=0, le=10)
    volume_min: float = Field(..., gt=0.0)
    volume_max: float = Field(..., gt=0.0)
    volume_step: float = Field(..., gt=0.0)
    contract_size_hint: float = Field(..., gt=0.0)

    @model_validator(mode="after")
    def validate_volume_range(self) -> "SymbolContract":
        if self.volume_max < self.volume_min:
            raise ValueError("volume_max must be greater than or equal to volume_min")
        return self


class SymbolRegistry(BaseModel):
    symbols: Dict[str, SymbolContract] = Field(..., min_length=1)

    @field_validator("symbols")
    @classmethod
    def validate_symbol_keys(cls, value: Dict[str, SymbolContract]) -> Dict[str, SymbolContract]:
        cleaned: Dict[str, SymbolContract] = {}

        for key, contract in value.items():
            symbol = key.strip()
            if not symbol:
                raise ValueError("symbol.yaml contains an empty symbol key")
            cleaned[symbol] = contract

        if not cleaned:
            raise ValueError("symbol.yaml must define at least one symbol contract")

        return cleaned


class FeatureSnapshot(BaseModel):
    snapshot_id: str = Field(..., min_length=8)
    symbol: str = Field(..., min_length=1)
    timeframe: str = Field(..., min_length=1)
    bar_time: datetime

    ema20: float
    ema50: float
    ema200: float
    ema20_slope: float
    ema_spread_ratio: float

    rsi14: float
    macd_line: float
    macd_signal: float
    macd_hist: float

    atr14: float
    bb_upper: float
    bb_mid: float
    bb_lower: float
    bb_width: float

    adx14: float
    di_plus: float
    di_minus: float

    swing_high: float
    swing_low: float
    dist_swing_high_atr: float
    dist_swing_low_atr: float

    breakout_state: BreakoutState
    retest_state: BreakoutState
    spread: float
    session: SessionType
    open_position_flag: bool

    @field_validator("rsi14")
    @classmethod
    def validate_rsi(cls, value: float) -> float:
        if not 0.0 <= value <= 100.0:
            raise ValueError("rsi14 must be between 0 and 100")
        return value

    @field_validator("adx14", "di_plus", "di_minus")
    @classmethod
    def validate_non_negative_index(cls, value: float) -> float:
        if value < 0.0:
            raise ValueError("ADX and DMI values must be non-negative")
        return value


class CandidateSetup(BaseModel):
    candidate_id: str = Field(..., min_length=8)
    snapshot_id: str = Field(..., min_length=8)
    setup_type: SetupType
    direction: Direction
    candidate_entry_min: float = Field(..., gt=0.0)
    candidate_entry_max: float = Field(..., gt=0.0)
    invalidation_anchor: float = Field(..., gt=0.0)
    created_at: datetime

    @model_validator(mode="after")
    def validate_entry_zone(self) -> "CandidateSetup":
        if self.candidate_entry_min > self.candidate_entry_max:
            raise ValueError("candidate_entry_min must be <= candidate_entry_max")
        return self


class AIDecision(BaseModel):
    candidate_id: str = Field(..., min_length=8)
    decision: Direction
    approved: bool
    confidence: float = Field(..., ge=0.0, le=1.0)

    entry_min: float = Field(..., gt=0.0)
    entry_max: float = Field(..., gt=0.0)
    stop_loss: float = Field(..., gt=0.0)

    setup_quality: float = Field(..., ge=0.0, le=1.0)
    trend_alignment: float = Field(..., ge=0.0, le=1.0)
    regime_fit: float = Field(..., ge=0.0, le=1.0)
    exhaustion_risk: float = Field(..., ge=0.0, le=1.0)

    reason: str = Field(..., min_length=3, max_length=300)
    model_name: str = Field(..., min_length=1)
    prompt_version: str = Field(..., min_length=1)
    latency_ms: int = Field(..., ge=0)
    valid_response: bool = True

    @model_validator(mode="after")
    def validate_entry_bounds(self) -> "AIDecision":
        if self.entry_min > self.entry_max:
            raise ValueError("entry_min must be <= entry_max")
        return self


class ExecutionPlan(BaseModel):
    candidate_id: str = Field(..., min_length=8)
    symbol: str = Field(..., min_length=1)
    direction: Direction
    order_type: OrderType = OrderType.MARKET

    planned_entry: float = Field(..., gt=0.0)
    stop_loss: float = Field(..., gt=0.0)
    take_profit: float = Field(..., gt=0.0)
    lot_size: float = Field(..., gt=0.0)
    rr: float = Field(..., gt=0.0)
    spread_at_execution: float = Field(..., ge=0.0)

    @model_validator(mode="after")
    def validate_price_relationships(self) -> "ExecutionPlan":
        if self.direction == Direction.BUY:
            if not (self.stop_loss < self.planned_entry < self.take_profit):
                raise ValueError("BUY plan must satisfy stop_loss < planned_entry < take_profit")
        else:
            if not (self.take_profit < self.planned_entry < self.stop_loss):
                raise ValueError("SELL plan must satisfy take_profit < planned_entry < stop_loss")
        return self


class ExecutionResult(BaseModel):
    execution_id: str = Field(..., min_length=8)
    candidate_id: str = Field(..., min_length=8)
    status: ExecutionStatus
    broker_order_id: Optional[str] = None
    filled_price: Optional[float] = None
    sent_at: datetime
    message: str = Field(..., min_length=1)


class OutcomeRecord(BaseModel):
    execution_id: str = Field(..., min_length=8)
    closed_at: datetime
    pnl: float
    pnl_r: float
    hit_1r: bool
    hit_2r: bool
    positive_at_10_bars: bool
    mfe: float
    mae: float
    close_reason: str = Field(..., min_length=1)