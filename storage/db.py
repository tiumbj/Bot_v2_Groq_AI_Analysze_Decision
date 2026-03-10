from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class DatabaseManager:
    def __init__(self, sqlite_path: str) -> None:
        self.sqlite_path = Path(sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.sqlite_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            self._create_feature_snapshots_table(cursor)
            self._create_candidates_table(cursor)
            self._create_ai_decisions_table(cursor)
            self._create_executions_table(cursor)
            self._create_outcomes_table(cursor)
            self._create_model_runs_table(cursor)
            self._create_runtime_state_table(cursor)

    @staticmethod
    def _create_feature_snapshots_table(cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS feature_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                bar_time TEXT NOT NULL,

                ema20 REAL NOT NULL,
                ema50 REAL NOT NULL,
                ema200 REAL NOT NULL,
                ema20_slope REAL NOT NULL,
                ema_spread_ratio REAL NOT NULL,

                rsi14 REAL NOT NULL,
                macd_line REAL NOT NULL,
                macd_signal REAL NOT NULL,
                macd_hist REAL NOT NULL,

                atr14 REAL NOT NULL,
                bb_upper REAL NOT NULL,
                bb_mid REAL NOT NULL,
                bb_lower REAL NOT NULL,
                bb_width REAL NOT NULL,

                adx14 REAL NOT NULL,
                di_plus REAL NOT NULL,
                di_minus REAL NOT NULL,

                swing_high REAL NOT NULL,
                swing_low REAL NOT NULL,
                dist_swing_high_atr REAL NOT NULL,
                dist_swing_low_atr REAL NOT NULL,

                breakout_state TEXT NOT NULL,
                retest_state TEXT NOT NULL,
                spread REAL NOT NULL,
                session TEXT NOT NULL,
                open_position_flag INTEGER NOT NULL
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_feature_snapshots_bar_time ON feature_snapshots(bar_time)"
        )

    @staticmethod
    def _create_candidates_table(cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                setup_type TEXT NOT NULL,
                direction TEXT NOT NULL,
                candidate_entry_min REAL NOT NULL,
                candidate_entry_max REAL NOT NULL,
                invalidation_anchor REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(snapshot_id) REFERENCES feature_snapshots(snapshot_id)
            )
            """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_candidates_snapshot_id ON candidates(snapshot_id)"
        )

    @staticmethod
    def _create_ai_decisions_table(cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_decisions (
                candidate_id TEXT PRIMARY KEY,
                model_name TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                decision TEXT NOT NULL,
                approved INTEGER NOT NULL,
                confidence REAL NOT NULL,
                entry_min REAL NOT NULL,
                entry_max REAL NOT NULL,
                stop_loss REAL NOT NULL,
                setup_quality REAL NOT NULL,
                trend_alignment REAL NOT NULL,
                regime_fit REAL NOT NULL,
                exhaustion_risk REAL NOT NULL,
                reason TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                valid_response INTEGER NOT NULL,
                FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
            )
            """
        )

    @staticmethod
    def _create_executions_table(cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS executions (
                execution_id TEXT PRIMARY KEY,
                candidate_id TEXT NOT NULL,
                final_entry REAL NOT NULL,
                final_stop_loss REAL NOT NULL,
                final_take_profit REAL NOT NULL,
                lot_size REAL NOT NULL,
                rr REAL NOT NULL,
                order_type TEXT NOT NULL,
                spread_at_execution REAL NOT NULL,
                slippage REAL,
                sent_at TEXT NOT NULL,
                execution_status TEXT NOT NULL,
                broker_order_id TEXT,
                message TEXT,
                FOREIGN KEY(candidate_id) REFERENCES candidates(candidate_id)
            )
            """
        )

    @staticmethod
    def _create_outcomes_table(cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS outcomes (
                execution_id TEXT PRIMARY KEY,
                closed_at TEXT NOT NULL,
                pnl REAL NOT NULL,
                pnl_r REAL NOT NULL,
                hit_1r INTEGER NOT NULL,
                hit_2r INTEGER NOT NULL,
                positive_at_10_bars INTEGER NOT NULL,
                mfe REAL NOT NULL,
                mae REAL NOT NULL,
                close_reason TEXT NOT NULL,
                FOREIGN KEY(execution_id) REFERENCES executions(execution_id)
            )
            """
        )

    @staticmethod
    def _create_model_runs_table(cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS model_runs (
                model_version TEXT PRIMARY KEY,
                train_start TEXT NOT NULL,
                train_end TEXT NOT NULL,
                rows_used INTEGER NOT NULL,
                label_name TEXT NOT NULL,
                auc REAL,
                pr_auc REAL,
                brier_score REAL,
                notes TEXT
            )
            """
        )

    @staticmethod
    def _create_runtime_state_table(cursor: sqlite3.Cursor) -> None:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_state (
                state_key TEXT PRIMARY KEY,
                state_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )