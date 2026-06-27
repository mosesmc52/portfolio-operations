# services/reporting/monthly_reporting_service.py
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from fees.models import FundExpense
from funds.models import Fund
from performance.models import MonthlySnapshot, NAVSnapshot
from reporting.services.monte_carlo_chart import build_nav_monte_carlo_chart
from services.llm.openai_client import OpenAITextService
from services.market_data.price_provider import YFinancePriceProvider


def _markdown_to_html(md: str) -> str:
    import markdown

    return markdown.markdown(
        md or "",
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )


def _markdown_to_plain(md: str) -> str:
    s = md or ""
    s = re.sub(r"^\s{0,3}#{1,6}\s+", "", s, flags=re.MULTILINE)
    s = s.replace("**", "").replace("__", "")
    s = s.replace("*", "")
    s = re.sub(r"^\s*-\s+", "• ", s, flags=re.MULTILINE)
    return s.strip()


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _to_pct_str(x: Optional[Decimal], *, ndp: int = 2) -> str:
    if x is None:
        return "N/A"
    return f"{(x * Decimal('100')):.{ndp}f}%"


def _to_signed_pct_str(x: Optional[Decimal], *, ndp: int = 1) -> str:
    if x is None:
        return "N/A"
    sign = "+" if x >= 0 else ""
    return f"{sign}{(x * Decimal('100')):.{ndp}f}%"


def _to_currency_str(x: Optional[Decimal], *, ndp: int = 2) -> str:
    if x is None:
        return "N/A"
    return f"${x:,.{ndp}f}"


def _to_decimal_str(x: Optional[Decimal], *, ndp: int = 2) -> str:
    if x is None:
        return "N/A"
    return f"{x:.{ndp}f}"


def _compute_max_drawdown(nav: pd.Series) -> Optional[Decimal]:
    if nav is None or len(nav) < 2:
        return None
    running_max = nav.cummax()
    dd = (nav / running_max) - 1.0
    m = float(dd.min())
    if not np.isfinite(m):
        return None
    return Decimal(str(m))


def _get_latest_nav_on_or_before(*, fund: Fund, d: date) -> Optional[NAVSnapshot]:
    return NAVSnapshot.objects.filter(fund=fund, date__lte=d).order_by("-date").first()


def _get_nav_series_window(*, fund: Fund, start: date, end: date) -> pd.DataFrame:
    qs = (
        NAVSnapshot.objects.filter(fund=fund, date__gte=start, date__lte=end)
        .order_by("date")
        .values("date", "nav_per_unit")
    )
    rows = list(qs)
    if not rows:
        return pd.DataFrame(columns=["date", "nav_per_unit"])
    df = pd.DataFrame(rows)
    df["nav_per_unit"] = df["nav_per_unit"].astype(float)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def _sum_mgmt_fees(*, fund: Fund, start: date, end: date) -> Decimal:
    return FundExpense.objects.filter(
        fund=fund,
        expense_type=FundExpense.TYPE_MGMT_FEE,
        as_of_date__gte=start,
        as_of_date__lte=end,
    ).aggregate(s=Coalesce(Sum("amount"), Decimal("0.00"))).get("s") or Decimal("0.00")


def _get_earliest_nav_on_or_after(*, fund: Fund, d: date):
    return NAVSnapshot.objects.filter(fund=fund, date__gte=d).order_by("date").first()


def _get_monthly_snapshot(
    *, fund: Fund, year: int, month: int
) -> Optional[MonthlySnapshot]:
    return MonthlySnapshot.objects.filter(
        fund=fund,
        as_of_month__year=year,
        as_of_month__month=month,
    ).first()


def _compute_cagr(
    *, start_nav: Decimal, end_nav: Decimal, start_date: date, end_date: date
) -> Optional[Decimal]:
    if start_nav <= 0 or end_nav <= 0 or end_date <= start_date:
        return None
    years = Decimal(str((end_date - start_date).days / 365.25))
    if years <= 0:
        return None
    return (end_nav / start_nav) ** (Decimal("1") / years) - Decimal("1")


def _compute_annualized_sharpe(nav: pd.Series) -> Optional[Decimal]:
    if nav is None or len(nav) < 3:
        return None
    rets = nav.astype(float).pct_change().dropna()
    if len(rets) < 2:
        return None
    vol = rets.std(ddof=1)
    if not np.isfinite(vol) or vol <= 0:
        return None
    sharpe = (rets.mean() / vol) * np.sqrt(252.0)
    if not np.isfinite(sharpe):
        return None
    return Decimal(str(sharpe))


def _build_monthly_returns_table(
    *, fund: Fund, period_end: date, years_back: int = 4
) -> list[dict]:
    start = date(period_end.year - years_back + 1, 1, 1)
    qs = (
        NAVSnapshot.objects.filter(fund=fund, date__gte=start, date__lte=period_end)
        .order_by("date")
        .values("date", "nav_per_unit")
    )
    rows = list(qs)
    if not rows:
        return []

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["nav_per_unit"] = df["nav_per_unit"].astype(float)
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month

    month_end = df.groupby(["year", "month"], as_index=False).last()
    month_end["prev_nav"] = month_end["nav_per_unit"].shift(1)
    month_end["month_return"] = (
        month_end["nav_per_unit"] / month_end["prev_nav"]
    ) - 1.0
    month_end["month_return"] = month_end["month_return"].where(
        month_end["year"].eq(month_end["year"].shift(1)),
        np.nan,
    )

    labels = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    out: list[dict] = []
    for year in sorted(month_end["year"].unique()):
        ydf = month_end[month_end["year"] == year]
        month_map = {int(row["month"]): row["month_return"] for _, row in ydf.iterrows()}
        first_idx = ydf.index[0]
        year_total = None
        prev_nav = month_end.loc[first_idx, "prev_nav"]
        if prev_nav and np.isfinite(prev_nav) and prev_nav > 0:
            year_total = Decimal(str((ydf.iloc[-1]["nav_per_unit"] / prev_nav) - 1.0))

        months = []
        for idx, label in enumerate(labels, start=1):
            raw = month_map.get(idx)
            if raw is None or not np.isfinite(raw):
                months.append({"label": label, "value": "—", "class_name": ""})
                continue
            dec = Decimal(str(raw))
            months.append(
                {
                    "label": label,
                    "value": _to_signed_pct_str(dec),
                    "class_name": "pos" if dec >= 0 else "neg",
                }
            )

        out.append(
            {
                "year": str(year),
                "months": months,
                "year_total": _to_signed_pct_str(year_total)
                if year_total is not None
                else "—",
            }
        )
    return out


def _split_commentary_sections(commentary: str) -> tuple[list[str], list[str]]:
    plain = _markdown_to_plain(commentary)
    bullets: list[str] = []
    paragraphs: list[str] = []
    current: list[str] = []

    for raw in plain.splitlines():
        line = raw.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        if line.startswith("• "):
            bullets.append(line[2:].strip())
            continue
        current.append(line)

    if current:
        paragraphs.append(" ".join(current).strip())

    return bullets[:5], paragraphs[:4]


@dataclass
class MonthlyReportResult:
    fund_id: int
    fund_strategy_code: str
    period_start: date
    period_end: date
    nav_start_date: date
    nav_end_date: date
    nav_start: Decimal
    nav_end: Decimal
    fund_return: Decimal
    spy_return: Optional[Decimal]
    max_drawdown: Optional[Decimal]
    mgmt_fee_total: Decimal
    commentary: str
    html: str
    pdf_bytes: bytes
    forecast_chart_png: bytes


class MonthlyReportingService:
    """
    Monthly reporting agent that:
      - computes fund performance from NAVSnapshot (NAV per unit)
      - benchmarks vs a configured monthly snapshot benchmark, defaulting to SPY
      - includes management fee totals from FundExpense
      - creates a Monte Carlo forecast chart based on historical NAV returns
      - uses OpenAI to generate commentary
      - renders HTML and PDF from the same Django template
    """

    def __init__(
        self,
        *,
        llm: Optional[OpenAITextService] = None,
        price_provider: Optional[YFinancePriceProvider] = None,
        llm_model: str = "gpt-5.2",
    ):
        self.llm = llm or OpenAITextService()
        self.price_provider = price_provider or YFinancePriceProvider()
        self.llm_model = llm_model

    def generate_monthly_report(
        self,
        *,
        fund_id: int,
        year: int,
        month: int,
        horizon_days: int = 42,
        n_sims: int = 2000,
        hist_lookback_days: int = 365,
    ) -> MonthlyReportResult:
        fund = Fund.objects.get(id=fund_id)
        period_start, period_end = _month_bounds(year, month)
        monthly_snapshot = _get_monthly_snapshot(fund=fund, year=year, month=month)

        nav_start_obj = _get_latest_nav_on_or_before(fund=fund, d=period_start)
        if not nav_start_obj:
            nav_start_obj = _get_earliest_nav_on_or_after(fund=fund, d=period_start)

        nav_end_obj = _get_latest_nav_on_or_before(fund=fund, d=period_end)

        if not nav_start_obj or not nav_end_obj:
            raise ValueError(
                f"Missing NAVSnapshot boundaries for fund={fund.strategy_code}. "
                f"Need NAV near {period_start}..{period_end}. "
                f"(start={getattr(nav_start_obj,'date',None)}, end={getattr(nav_end_obj,'date',None)})"
            )

        nav_start = Decimal(nav_start_obj.nav_per_unit)
        nav_end = Decimal(nav_end_obj.nav_per_unit)
        if nav_start <= 0:
            raise ValueError("nav_start must be > 0")

        fund_return = (nav_end / nav_start) - Decimal("1")

        nav_month_df = _get_nav_series_window(fund=fund, start=period_start, end=period_end)
        max_dd = None
        if not nav_month_df.empty and len(nav_month_df) >= 2:
            nav_series = nav_month_df.set_index("date")["nav_per_unit"]
            max_dd = _compute_max_drawdown(nav_series)

        mgmt_fee_total = _sum_mgmt_fees(fund=fund, start=period_start, end=period_end)
        benchmark_symbol = monthly_snapshot.benchmark_symbol if monthly_snapshot else "SPY"

        benchmark_series_month = self.price_provider.get_daily_close(
            symbol=benchmark_symbol,
            start=period_start,
            end=period_end + timedelta(days=1),
        )
        spy_return = None
        if len(benchmark_series_month.close) >= 2 and benchmark_series_month.close[0] > 0:
            spy_return = Decimal(
                str(
                    (benchmark_series_month.close[-1] / benchmark_series_month.close[0])
                    - 1.0
                )
            )

        hist_start = period_end - timedelta(days=hist_lookback_days)
        nav_hist_df = _get_nav_series_window(fund=fund, start=hist_start, end=period_end)
        if nav_hist_df.empty or len(nav_hist_df) < 10:
            nav_hist_df = _get_nav_series_window(
                fund=fund, start=fund.inception_date, end=period_end
            )

        benchmark_series_hist = self.price_provider.get_daily_close(
            symbol=benchmark_symbol,
            start=min(hist_start, period_start - timedelta(days=365)),
            end=period_end + timedelta(days=1),
        )

        chart_res = build_nav_monte_carlo_chart(
            hist_dates=nav_hist_df["date"].tolist(),
            hist_nav=[Decimal(str(x)) for x in nav_hist_df["nav_per_unit"].tolist()],
            sim_start_date=nav_end_obj.date,
            horizon_days=horizon_days,
            n_sims=n_sims,
            title="NAV History vs Benchmark",
            benchmark_dates=benchmark_series_hist.dates,
            benchmark_close=benchmark_series_hist.close,
        )
        forecast_chart_png = chart_res.png_bytes

        nav_all_df = _get_nav_series_window(fund=fund, start=fund.inception_date, end=period_end)
        inception_return = None
        cagr = None
        sharpe = None
        ytd_return = None
        if not nav_all_df.empty:
            nav_all_df = nav_all_df.sort_values("date")
            nav_all_series = nav_all_df.set_index("date")["nav_per_unit"]
            inception_nav = Decimal(str(nav_all_df.iloc[0]["nav_per_unit"]))
            first_nav_date = nav_all_df.iloc[0]["date"]

            if inception_nav > 0:
                inception_return = (nav_end / inception_nav) - Decimal("1")
                cagr = _compute_cagr(
                    start_nav=inception_nav,
                    end_nav=nav_end,
                    start_date=first_nav_date,
                    end_date=nav_end_obj.date,
                )

            sharpe = _compute_annualized_sharpe(nav_all_series)

            ytd_anchor_date = date(period_end.year, 1, 1)
            ytd_anchor = _get_latest_nav_on_or_before(
                fund=fund, d=ytd_anchor_date
            ) or _get_earliest_nav_on_or_after(fund=fund, d=ytd_anchor_date)
            if ytd_anchor:
                ytd_nav = Decimal(ytd_anchor.nav_per_unit)
                if ytd_nav > 0:
                    ytd_return = (nav_end / ytd_nav) - Decimal("1")

        system = (
            "You are an investment reporting analyst. "
            "Write concise, professional monthly commentary for a systematic ETF strategy. "
            "Avoid guarantees or promissory language. "
            "Use neutral, compliance-safe phrasing."
        )
        benchmark_return_prompt = (
            f"{spy_return:.2%}" if spy_return is not None else "N/A"
        )
        user = f"""
Fund: {fund.strategy_code}
Period: {period_start} to {period_end}

NAV:
- Start NAV ({nav_start_obj.date}): {nav_start}
- End NAV ({nav_end_obj.date}): {nav_end}

Performance:
- Fund return: {fund_return:.2%}
- Benchmark ({benchmark_symbol}) return: {benchmark_return_prompt}
- Max drawdown (month, from NAV snapshots): {str(max_dd) if max_dd is not None else "N/A"}
- Management fee accrued (month): ${mgmt_fee_total}

Strategy operations:
- Weekly rebalance
- 3–5 ETFs
- Systematic rules-based allocation

Please output:
1) 3–5 bullet highlights
2) 1 short paragraph on relative performance vs the benchmark
3) 1 short paragraph on risk (drawdown/volatility framing; no predictions)
4) 1 operational note: rebalancing cadence + ETF universe size
5) 1 disclosure line: "Past performance is not indicative of future results."
""".strip()

        commentary = self.llm.generate_commentary(
            system=system, user=user, model=self.llm_model
        ).text

        commentary_bullets, commentary_paragraphs = _split_commentary_sections(commentary)
        monthly_returns = _build_monthly_returns_table(fund=fund, period_end=period_end)

        html = self._render_html(
            fund=fund,
            monthly_snapshot=monthly_snapshot,
            period_start=period_start,
            period_end=period_end,
            nav_start=nav_start,
            nav_end=nav_end,
            nav_start_date=nav_start_obj.date,
            nav_end_date=nav_end_obj.date,
            fund_return=fund_return,
            spy_return=spy_return,
            max_drawdown=max_dd,
            mgmt_fee_total=mgmt_fee_total,
            commentary=commentary,
            forecast_chart_png=forecast_chart_png,
            benchmark_symbol=benchmark_symbol,
            ytd_return=ytd_return,
            inception_return=inception_return,
            cagr=cagr,
            sharpe=sharpe,
            monthly_returns=monthly_returns,
            commentary_bullets=commentary_bullets,
            commentary_paragraphs=commentary_paragraphs,
        )
        pdf_bytes = self._render_pdf(html=html)

        return MonthlyReportResult(
            fund_id=fund.id,
            fund_strategy_code=fund.strategy_code,
            period_start=period_start,
            period_end=period_end,
            nav_start_date=nav_start_obj.date,
            nav_end_date=nav_end_obj.date,
            nav_start=nav_start,
            nav_end=nav_end,
            fund_return=fund_return,
            spy_return=spy_return,
            max_drawdown=max_dd,
            mgmt_fee_total=mgmt_fee_total,
            commentary=commentary,
            html=html,
            pdf_bytes=pdf_bytes,
            forecast_chart_png=forecast_chart_png,
        )

    def _render_html(
        self,
        *,
        fund: Fund,
        monthly_snapshot: Optional[MonthlySnapshot],
        period_start: date,
        period_end: date,
        nav_start: Decimal,
        nav_end: Decimal,
        nav_start_date: date,
        nav_end_date: date,
        fund_return: Decimal,
        spy_return: Optional[Decimal],
        max_drawdown: Optional[Decimal],
        mgmt_fee_total: Decimal,
        commentary: str,
        forecast_chart_png: bytes,
        benchmark_symbol: str,
        ytd_return: Optional[Decimal],
        inception_return: Optional[Decimal],
        cagr: Optional[Decimal],
        sharpe: Optional[Decimal],
        monthly_returns: list[dict],
        commentary_bullets: list[str],
        commentary_paragraphs: list[str],
    ) -> str:
        chart_b64 = base64.b64encode(forecast_chart_png).decode("ascii")
        return render_to_string(
            "reporting/monthly_report.html",
            {
                "fund": fund,
                "monthly_snapshot": monthly_snapshot,
                "period_start": period_start,
                "period_end": period_end,
                "as_of_label": period_end.strftime("%B %d, %Y").upper(),
                "chart_data_uri": f"data:image/png;base64,{chart_b64}",
                "commentary_html": _markdown_to_html(commentary),
                "commentary_bullets": commentary_bullets,
                "commentary_paragraphs": commentary_paragraphs,
                "benchmark_symbol": benchmark_symbol,
                "fund_return_text": _to_signed_pct_str(fund_return),
                "benchmark_return_text": _to_signed_pct_str(spy_return),
                "ytd_return_text": _to_signed_pct_str(ytd_return),
                "inception_return_text": _to_signed_pct_str(inception_return),
                "cagr_text": _to_pct_str(cagr, ndp=1) if cagr is not None else "N/A",
                "sharpe_text": _to_decimal_str(sharpe),
                "max_drawdown_text": _to_signed_pct_str(max_drawdown),
                "nav_start_text": _to_decimal_str(nav_start),
                "nav_end_text": _to_decimal_str(nav_end),
                "nav_start_date": nav_start_date,
                "nav_end_date": nav_end_date,
                "fee_text": _to_currency_str(mgmt_fee_total),
                "aum_text": _to_currency_str(
                    getattr(monthly_snapshot, "aum_eom", None)
                ),
                "monthly_returns": monthly_returns,
                "inception_date": fund.inception_date,
            },
        )

    def _render_pdf(self, *, html: str) -> bytes:
        try:
            from weasyprint import HTML
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "WeasyPrint is required for monthly report PDF generation. "
                "Install project dependencies before running monthly reporting."
            ) from exc

        return HTML(string=html).write_pdf()
