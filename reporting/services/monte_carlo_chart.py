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
    bg = "#0e2347"
    accent = "#1baeea"
    fig = plt.figure(figsize=(12, 6))
    fig.patch.set_facecolor(bg)
    ax = plt.gca()
    ax.set_facecolor(bg)
    ax.axis("off")
    ax.text(
        0.5,
        0.60,
        title,
        ha="center",
        va="center",
        fontsize=16,
        fontweight="bold",
        color=accent,
    )
    ax.text(
        0.5,
        0.45,
        message,
        ha="center",
        va="center",
        fontsize=12,
        color=accent,
    )
    buf = BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=150, facecolor=bg, edgecolor=bg)
    plt.close(fig)
    return MCChartResult(png_bytes=buf.getvalue(), skipped=True, reason=message)


def _render_history_only(
    *,
    title: str,
    hist_dates: Sequence[date],
    hist_nav: Sequence[Decimal],
    benchmark_dates: Optional[Sequence[date]] = None,
    benchmark_close: Optional[Sequence[float]] = None,
    message: str = "",
) -> MCChartResult:
    if not hist_dates or not hist_nav:
        return _render_placeholder(title=title, message=message or "No NAV history available.")

    df = pd.DataFrame(
        {"date": pd.to_datetime(list(hist_dates)), "nav": [float(x) for x in hist_nav]}
    )
    df = df.sort_values("date").dropna()
    df["date"] = df["date"].dt.date
    if df.empty:
        return _render_placeholder(title=title, message=message or "No NAV history available.")

    start_nav = float(df.iloc[0]["nav"])
    hist_start_date = df.iloc[0]["date"]
    hist_end_date = df.iloc[-1]["date"]

    fig = plt.figure(figsize=(12, 6))
    ax = plt.gca()

    ax.plot(
        df["date"],
        df["nav"],
        linewidth=2.5,
        marker="o" if len(df) <= 12 else None,
        label="Historical NAV",
    )

    if (
        benchmark_dates
        and benchmark_close
        and len(benchmark_dates) == len(benchmark_close)
        and len(benchmark_close) > 1
        and start_nav > 0
    ):
        bdf = pd.DataFrame(
            {
                "date": pd.to_datetime(list(benchmark_dates)),
                "close": list(benchmark_close),
            }
        )
        bdf = bdf.sort_values("date").dropna()
        bdf["date"] = bdf["date"].dt.date
        bdf = bdf[
            (bdf["date"] >= hist_start_date) & (bdf["date"] <= hist_end_date)
        ].copy()
        if not bdf.empty:
            b0 = float(bdf.iloc[0]["close"])
            if b0 > 0:
                bdf["bench_norm"] = (bdf["close"] / b0) * start_nav
                ax.plot(
                    bdf["date"],
                    bdf["bench_norm"],
                    linewidth=1.75,
                    linestyle="--",
                    label="Benchmark (normalized)",
                )

    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("NAV per unit")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left")
    if message:
        ax.text(
            0.01,
            0.02,
            message,
            transform=ax.transAxes,
            fontsize=9,
            alpha=0.8,
            va="bottom",
        )

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
    Render historical NAV with optional benchmark overlay.
    Monte Carlo forecast is currently disabled in the report output.
    """
    return _render_history_only(
        title=title,
        hist_dates=hist_dates,
        hist_nav=hist_nav,
        benchmark_dates=benchmark_dates,
        benchmark_close=benchmark_close,
        message="",
    )
