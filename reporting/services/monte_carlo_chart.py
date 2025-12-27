# services/reporting/monte_carlo_chart.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


@dataclass
class MCChartResult:
    png_bytes: bytes
    skipped: bool = False
    reason: str = ""


def _dates_bdays(start: date, n: int) -> list[date]:
    out = []
    d = start
    while len(out) < n:
        d = d + timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def _render_placeholder(*, title: str, message: str) -> MCChartResult:
    fig = plt.figure(figsize=(12, 6))
    ax = plt.gca()
    ax.axis("off")
    ax.text(0.5, 0.60, title, ha="center", va="center", fontsize=16, fontweight="bold")
    ax.text(0.5, 0.45, message, ha="center", va="center", fontsize=12)
    buf = BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    return MCChartResult(png_bytes=buf.getvalue(), skipped=True, reason=message)


def build_nav_monte_carlo_chart(
    *,
    hist_dates: Sequence[date],
    hist_nav: Sequence[Decimal],
    sim_start_date: date,
    horizon_days: int = 42,
    n_sims: int = 2000,
    ci_lo_hi: tuple[float, float] = (0.05, 0.95),
    ci50_lo_hi: tuple[float, float] = (0.25, 0.75),
    title: str = "NAV Monte Carlo Forecast",
    benchmark_dates: Optional[Sequence[date]] = None,
    benchmark_close: Optional[Sequence[float]] = None,
    min_points: int = 10,
) -> MCChartResult:
    """
    If insufficient NAV history is available, returns a placeholder image and does NOT raise.
    """

    if len(hist_dates) < min_points or len(hist_nav) < min_points:
        return _render_placeholder(
            title=title,
            message=f"Forecast unavailable: need at least {min_points} NAV observations (have {len(hist_nav)}).",
        )

    df = pd.DataFrame(
        {"date": pd.to_datetime(list(hist_dates)), "nav": [float(x) for x in hist_nav]}
    )
    df = df.sort_values("date").dropna()
    df["date"] = df["date"].dt.date

    df_pre = df[df["date"] <= sim_start_date]
    if df_pre.empty:
        return _render_placeholder(
            title=title,
            message="Forecast unavailable: simulation start date is earlier than NAV history.",
        )

    start_nav = float(df_pre.iloc[-1]["nav"])

    df_fit = df[df["date"] <= sim_start_date].copy()
    df_fit["log_ret"] = np.log(df_fit["nav"]).diff()
    logrets = df_fit["log_ret"].dropna().values
    if logrets.size < 5:
        return _render_placeholder(
            title=title,
            message="Forecast unavailable: not enough return observations to estimate volatility.",
        )

    mu = float(np.mean(logrets))
    sigma = float(np.std(logrets, ddof=1))
    if not np.isfinite(mu) or not np.isfinite(sigma) or sigma <= 0:
        return _render_placeholder(
            title=title,
            message="Forecast unavailable: invalid volatility estimate (check NAV data quality).",
        )

    rng = np.random.default_rng(42)
    shocks = rng.standard_normal(size=(n_sims, horizon_days))
    sim_log_rets = mu + sigma * shocks
    sim_paths = np.exp(np.cumsum(sim_log_rets, axis=1)) * start_nav

    lo, hi = ci_lo_hi
    lo50, hi50 = ci50_lo_hi

    p_lo = np.quantile(sim_paths, lo, axis=0)
    p_hi = np.quantile(sim_paths, hi, axis=0)
    p_lo50 = np.quantile(sim_paths, lo50, axis=0)
    p_hi50 = np.quantile(sim_paths, hi50, axis=0)
    p_med = np.quantile(sim_paths, 0.50, axis=0)

    future_dates = _dates_bdays(sim_start_date, horizon_days)

    fig = plt.figure(figsize=(12, 6))
    ax = plt.gca()

    ax.plot(df["date"], df["nav"], linewidth=2, label="Historical NAV")

    if (
        benchmark_dates
        and benchmark_close
        and len(benchmark_dates) == len(benchmark_close)
        and len(benchmark_close) > 5
    ):
        bdf = pd.DataFrame(
            {
                "date": pd.to_datetime(list(benchmark_dates)),
                "close": list(benchmark_close),
            }
        )
        bdf["date"] = bdf["date"].dt.date
        bdf = bdf.sort_values("date")
        bdf_pre = bdf[bdf["date"] <= sim_start_date]
        if not bdf_pre.empty:
            b0 = float(bdf_pre.iloc[-1]["close"])
            if b0 > 0:
                bdf["bench_norm"] = (bdf["close"] / b0) * start_nav
                ax.plot(
                    bdf["date"],
                    bdf["bench_norm"],
                    linewidth=1.5,
                    label="Benchmark (SPY, normalized)",
                )

    ax.fill_between(
        future_dates, p_lo, p_hi, alpha=0.20, label="90% Confidence Interval"
    )
    ax.fill_between(
        future_dates, p_lo50, p_hi50, alpha=0.35, label="50% Confidence Interval"
    )
    ax.plot(
        future_dates, p_med, linestyle="--", linewidth=2, label="Median Simulated Path"
    )
    ax.axvline(
        sim_start_date, linestyle="--", linewidth=2, label="Simulation Start Date"
    )

    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("NAV per unit")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left")

    buf = BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)

    return MCChartResult(png_bytes=buf.getvalue(), skipped=False, reason="")
