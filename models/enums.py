from enum import Enum


class Environment(str, Enum):
    DEV = "dev"
    PROD = "prod"


class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class SetupType(str, Enum):
    TREND_PULLBACK_LONG = "trend_pullback_long"
    TREND_PULLBACK_SHORT = "trend_pullback_short"
    BREAKOUT_RETEST_LONG = "breakout_retest_long"
    BREAKOUT_RETEST_SHORT = "breakout_retest_short"


class SessionType(str, Enum):
    ASIA = "asia"
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "overlap"
    UNKNOWN = "unknown"


class BreakoutState(str, Enum):
    NONE = "none"
    PRE_BREAKOUT = "pre_breakout"
    BREAKOUT = "breakout"
    RETEST = "retest"
    FAILED_BREAKOUT = "failed_breakout"


class DecisionStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FILLED = "filled"
    REJECTED = "rejected"
    FAILED = "failed"


class CloseReason(str, Enum):
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TIME_EXIT = "time_exit"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class OrderType(str, Enum):
    MARKET = "market"