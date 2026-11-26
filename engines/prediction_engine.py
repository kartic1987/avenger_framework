import pandas as pd

class PredictionEngine:
    """Transparent baseline forecast using a rolling average; replace with validated ML models."""
    def forecast(self, values: list[float], periods: int = 3, window: int = 3) -> dict:
        if len(values) < 2: raise ValueError("Provide at least two historical numeric values.")
        if periods < 1 or periods > 24: raise ValueError("Periods must be between 1 and 24.")
        window = max(1, min(window, len(values)))
        baseline = sum(values[-window:]) / window
        return {"historical_values": values, "forecast": [round(baseline, 2)] * periods,
                "method": f"Flat forecast based on last {window}-period average",
                "warning": "Baseline demonstration only; assess seasonality and backtest before business use."}

    def forecast_csv(self, frame: pd.DataFrame, value_column: str, periods: int = 3):
        if value_column not in frame: raise ValueError("Selected value column does not exist.")
        values = pd.to_numeric(frame[value_column], errors="coerce").dropna().tolist()
        return self.forecast(values, periods)
