# services/reporting/monthly_reporting_service.py
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Optional, Sequence

import numpy as np
import pandas as pd
from django.db.models import Sum
from django.db.models.functions import Coalesce
from fees.models import FundExpense
from funds.models import Fund
from performance.models import NAVSnapshot
from reporting.services.monte_carlo_chart import build_nav_monte_carlo_chart
from services.llm.openai_client import OpenAITextService
from services.market_data.price_provider import YFinancePriceProvider

# ---------- helpers ----------


def _markdown_to_html(md: str) -> str:
    import markdown

    return markdown.markdown(
        md or "",
        extensions=["extra", "sane_lists"],
        output_format="html5",
    )


def _markdown_to_plain(md: str) -> str:
    s = md or ""
    # headings: "## X" -> "X"
    s = re.sub(r"^\s{0,3}#{1,6}\s+", "", s, flags=re.MULTILINE)
    # bold/italic markers
    s = s.replace("**", "").replace("__", "")
    s = s.replace("*", "")
    # bullets "- x" keep as "• x"
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


def _compute_max_drawdown(nav: pd.Series) -> Optional[Decimal]:
    """
    nav: float series indexed by date (ascending).
    Returns minimum drawdown (negative number), e.g. -0.12
    """
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


# ---------- result ----------


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

    # Optional: stored/embedded chart bytes for reuse
    forecast_chart_png: bytes


# ---------- main service ----------


class MonthlyReportingService:
    """
    Monthly reporting agent that:
      - computes fund performance from NAVSnapshot (NAV per unit)
      - benchmarks vs SPY (yfinance by default)
      - includes management fee totals from FundExpense
      - creates a Monte Carlo forecast chart based on historical NAV returns
      - uses OpenAI to generate commentary
      - renders HTML and PDF (reportlab) with the chart embedded
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
        horizon_days: int = 42,  # forecast business days (~2 months)
        n_sims: int = 2000,
        hist_lookback_days: int = 365,  # used for MC parameter estimation context
    ) -> MonthlyReportResult:
        fund = Fund.objects.get(id=fund_id)
        period_start, period_end = _month_bounds(year, month)

        nav_start_obj = _get_latest_nav_on_or_before(fund=fund, d=period_start)
        nav_end_obj = _get_latest_nav_on_or_before(fund=fund, d=period_end)
        if not nav_start_obj or not nav_end_obj:
            raise ValueError(
                f"Missing NAVSnapshot boundaries for fund={fund.strategy_code}. "
                f"Need NAV on/before {period_start} and {period_end}."
            )

        nav_start = Decimal(nav_start_obj.nav_per_unit)
        nav_end = Decimal(nav_end_obj.nav_per_unit)
        if nav_start <= 0:
            raise ValueError("nav_start must be > 0")

        fund_return = (nav_end / nav_start) - Decimal("1")

        # drawdown within month (based on available snapshots in month window)
        nav_month_df = _get_nav_series_window(
            fund=fund, start=period_start, end=period_end
        )
        max_dd = None
        if not nav_month_df.empty and len(nav_month_df) >= 2:
            nav_series = nav_month_df.set_index("date")["nav_per_unit"]
            max_dd = _compute_max_drawdown(nav_series)

        # management fees accrued during the month
        mgmt_fee_total = _sum_mgmt_fees(fund=fund, start=period_start, end=period_end)

        # benchmark SPY (month)
        spy_series_month = self.price_provider.get_daily_close(
            symbol="SPY",
            start=period_start,
            end=period_end + timedelta(days=1),
        )
        spy_return = None
        if len(spy_series_month.close) >= 2 and spy_series_month.close[0] > 0:
            spy_return = Decimal(
                str((spy_series_month.close[-1] / spy_series_month.close[0]) - 1.0)
            )

        # --- Monte Carlo forecast chart ---
        # Pull historical NAV for lookback window ending at period_end
        hist_start = period_end - timedelta(days=hist_lookback_days)
        nav_hist_df = _get_nav_series_window(
            fund=fund, start=hist_start, end=period_end
        )
        if nav_hist_df.empty or len(nav_hist_df) < 10:
            # fall back to all NAV snapshots up to period_end
            qs_all = (
                NAVSnapshot.objects.filter(fund=fund, date__lte=period_end)
                .order_by("date")
                .values("date", "nav_per_unit")
            )
            rows_all = list(qs_all)
            nav_hist_df = pd.DataFrame(rows_all)
            if not nav_hist_df.empty:
                nav_hist_df["nav_per_unit"] = nav_hist_df["nav_per_unit"].astype(float)
                nav_hist_df["date"] = pd.to_datetime(nav_hist_df["date"]).dt.date

        # For benchmark overlay on chart, fetch more history so the line looks continuous
        spy_series_hist = self.price_provider.get_daily_close(
            symbol="SPY",
            start=min(hist_start, period_start - timedelta(days=365)),
            end=period_end + timedelta(days=1),
        )

        chart_res = build_nav_monte_carlo_chart(
            hist_dates=nav_hist_df["date"].tolist(),
            hist_nav=[Decimal(str(x)) for x in nav_hist_df["nav_per_unit"].tolist()],
            sim_start_date=nav_end_obj.date,  # forecast from the last available NAV date at/within month-end
            horizon_days=horizon_days,
            n_sims=n_sims,
            title=f"{fund.strategy_code}: NAV History + Monte Carlo Forecast",
            benchmark_dates=spy_series_hist.dates,
            benchmark_close=spy_series_hist.close,
        )
        forecast_chart_png = chart_res.png_bytes

        # --- LLM commentary ---
        system = (
            "You are an investment reporting analyst. "
            "Write concise, professional monthly commentary for a systematic ETF strategy. "
            "Avoid guarantees or promissory language. "
            "Use neutral, compliance-safe phrasing."
        )
        user = f"""
Fund: {fund.strategy_code}
Period: {period_start} to {period_end}

NAV:
- Start NAV ({nav_start_obj.date}): {nav_start}
- End NAV ({nav_end_obj.date}): {nav_end}

Performance:
- Fund return: {fund_return:.4%}
- Max drawdown (month, from NAV snapshots): {str(max_dd) if max_dd is not None else "N/A"}
- Management fee accrued (month): ${mgmt_fee_total}

Benchmark:
spy_ret_str = f"{spy_return:.4%}" if spy_return is not None else "N/A"

Strategy operations:
- Weekly rebalance
- 3–5 ETFs
- Systematic rules-based allocation

Please output:
1) 3–5 bullet highlights
2) 1 short paragraph on relative performance vs SPY (if SPY return is available)
3) 1 short paragraph on risk (drawdown/volatility framing; no predictions)
4) 1 operational note: rebalancing cadence + ETF universe size
5) 1 disclosure line: "Past performance is not indicative of future results."
""".strip()

        commentary = self.llm.generate_commentary(
            system=system, user=user, model=self.llm_model
        ).text

        # --- Render HTML + PDF with embedded chart ---
        html = self._render_html(
            fund=fund,
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
        )

        pdf_bytes = self._render_pdf(
            fund=fund,
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
        )

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
    ) -> str:
        chart_b64 = base64.b64encode(forecast_chart_png).decode("ascii")
        spy_text = _to_pct_str(spy_return)
        dd_text = _to_pct_str(max_drawdown) if max_drawdown is not None else "N/A"

        commentary_html = _markdown_to_html(commentary)

        return f"""
<html>
  <head>
    <meta charset="utf-8"/>
    <title>{fund.strategy_code} Monthly Report</title>
    <style>
      body {{ font-family: Arial, sans-serif; margin: 32px; }}
      h1 {{ margin: 0 0 4px 0; }}
      .meta {{ color: #555; margin-bottom: 16px; }}
      .grid {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin-bottom: 16px;
      }}
      .box {{
        border: 1px solid #ddd;
        padding: 12px;
        border-radius: 10px;
      }}
      .kpi b {{
        display: inline-block;
        width: 175px;
      }}
      pre {{
        white-space: pre-wrap;
        margin: 0;
      }}
      img {{
        max-width: 100%;
        border: 1px solid #eee;
        border-radius: 10px;
      }}
      .small {{
        font-size: 12px;
        color: #666;
      }}
      .box ul {{ margin: 8px 0 8px 18px; }}
      .box li {{ margin: 4px 0; }}
      .box h1, .box h2, .box h3 {{ margin: 8px 0; }}
    </style>
  </head>
  <body>
    <h1>{fund.strategy_code} — Monthly Tear Sheet</h1>
    <div class="meta">{period_start} to {period_end}</div>

    <div class="grid">
      <div class="box">
        <div class="kpi"><b>Fund return</b> {fund_return:.2%}</div>
        <div class="kpi"><b>SPY return</b> {spy_text}</div>
        <div class="kpi"><b>Max drawdown</b> {dd_text}</div>
        <div class="kpi"><b>NAV start ({nav_start_date})</b> {nav_start:.2f}</div>
        <div class="kpi"><b>NAV end ({nav_end_date})</b> {nav_end:.2f}</div>
        <div class="kpi"><b>Mgmt fee accrued</b> ${mgmt_fee_total}</div>
      </div>

      <div class="box">
        <b>Forecast (Illustrative Monte Carlo)</b>
        <div class="small">Simulation based on historical NAV volatility; does not predict future results.</div>
        <div style="margin-top:10px;">
          <img src="data:image/png;base64,{chart_b64}" />
        </div>
      </div>
    </div>

    <h2>Commentary</h2>
    <div class="box">{commentary_html}</div>

    <h3>Disclosures</h3>
    <div class="small">
      For informational purposes only. Past performance is not indicative of future results.
      Systematic strategy; weekly rebalance; 3–5 ETFs. Monte Carlo forecasts are illustrative.
    </div>
  </body>
</html>
""".strip()

    def _render_pdf(
        self,
        *,
        fund: Fund,
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
    ) -> bytes:
        """
        PDF rendering using reportlab with embedded chart image.
        """
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=LETTER)
        width, height = LETTER

        left = 72
        y = height - 72

        # Title
        c.setFont("Helvetica-Bold", 14)
        c.drawString(left, y, f"{fund.strategy_code} — Monthly Report")
        y -= 16
        c.setFont("Helvetica", 10)
        c.drawString(left, y, f"Period: {period_start} to {period_end}")
        y -= 18

        # KPIs
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left, y, "Performance Summary")
        y -= 14
        c.setFont("Helvetica", 10)

        def line(label: str, value: str):
            nonlocal y
            c.drawString(left, y, f"{label}: {value}")
            y -= 12

        line("Fund return", f"{fund_return:.2%}")
        line("SPY return", f"{spy_return:.2%}" if spy_return is not None else "N/A")
        line(
            "Max drawdown (month)",
            f"{max_drawdown:.2%}" if max_drawdown is not None else "N/A",
        )
        line("NAV start", f"{nav_start} ({nav_start_date})")
        line("NAV end", f"{nav_end} ({nav_end_date})")
        line("Mgmt fee accrued (month)", f"${mgmt_fee_total}")
        y -= 10

        # Chart
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left, y, "NAV History + Monte Carlo Forecast (Illustrative)")
        y -= 8
        c.setFont("Helvetica", 9)
        c.drawString(
            left,
            y,
            "Simulation based on historical NAV volatility; does not predict future results.",
        )
        y -= 10

        img = ImageReader(BytesIO(forecast_chart_png))
        # Reserve space ~ 4.0 inches tall
        img_w = width - 2 * left
        img_h = 260
        if y - img_h < 72:
            c.showPage()
            y = height - 72
        c.drawImage(
            img,
            left,
            y - img_h,
            width=img_w,
            height=img_h,
            preserveAspectRatio=True,
            mask="auto",
        )
        y -= img_h + 18

        # Commentary
        c.setFont("Helvetica-Bold", 11)
        c.drawString(left, y, "Commentary")
        y -= 14
        c.setFont("Helvetica", 10)

        # Simple wrapping
        max_chars = 110
        commentary_plain = _markdown_to_plain(commentary)
        for raw_line in commentary_plain.splitlines():
            text = raw_line.strip()
            if not text:
                y -= 10
                continue

            # wrap long lines
            while len(text) > 0:
                chunk = text[:max_chars]
                text = text[max_chars:]
                if y < 72:
                    c.showPage()
                    y = height - 72
                    c.setFont("Helvetica", 10)
                c.drawString(left, y, chunk)
                y -= 12

        # Disclosures
        if y < 96:
            c.showPage()
            y = height - 72
        y -= 10
        c.setFont("Helvetica-Bold", 10)
        c.drawString(left, y, "Disclosures")
        y -= 12
        c.setFont("Helvetica", 9)
        c.drawString(
            left,
            y,
            "For informational purposes only. Past performance is not indicative of future results.",
        )
        y -= 11
        c.drawString(
            left,
            y,
            "Systematic strategy; weekly rebalance; 3–5 ETFs. Monte Carlo forecasts are illustrative.",
        )

        c.showPage()
        c.save()
        return buf.getvalue()
