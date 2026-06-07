from __future__ import annotations

from dataclasses import dataclass

from src.report import build_reports
from src.strategy_straddle import run_straddle_strategy


@dataclass
class BacktestEngine:
    provider: object
    config: dict

    def run(self, start_date=None, end_date=None) -> dict:
        trades = run_straddle_strategy(self.provider, self.config, start_date=start_date, end_date=end_date)
        return build_reports(trades)

