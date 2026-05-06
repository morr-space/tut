import os
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import FinanceDataReader as fdr
import pandas as pd


EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]
EMAIL_TO = os.environ.get("EMAIL_TO", EMAIL_USER)

MARKET = "KOSDAQ"
MARKET_INDEX = "KQ11"
TEST_MODE = True

TEST_CODES = [
    "247540",  # 에코프로비엠
    "086520",  # 에코프로
    "041510",  # 에스엠
    "035760",  # CJ ENM
    "028300",  # HLB
]

PARAMS = {
    "listed_years_min": 2,
    "price_min": 2_000,
    "price_max": 500_000,
    "nratio_min": 0.02,
    "nratio_max": 0.12,
    "value_krw_20d_min": 10_000_000_000,
}

def get_latest_market_date():
    end = datetime.now()
    start = end - timedelta(days=10)
    df = fdr.DataReader(MARKET_INDEX, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    if df.empty:
        raise ValueError(f"{MARKET} 지수 데이터를 가져오지 못했습니다.")
    return df.index[-1].strftime("%Y-%m-%d")


def is_today_market_data(latest_market_date):
    return latest_market_date == datetime.now().strftime("%Y-%m-%d")


def get_stocks():
    stocks = fdr.StockListing(MARKET)[["Code", "Name", "Market"]].copy()
    if TEST_MODE:
        stocks = stocks[stocks["Code"].isin(TEST_CODES)].copy()
    return stocks


def get_price_data(code):
    end = datetime.now()
    start = end - timedelta(days=365 * 4)
    df = fdr.DataReader(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    if df.empty or len(df) < 60:
        return None
    return df


def calc_tr(df):
    prev_close = df["Close"].shift(1)
    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - prev_close).abs()
    tr3 = (df["Low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    tr.iloc[0] = df.iloc[0]["High"] - df.iloc[0]["Low"]
    return tr


def evaluate_step1(df):
    df = df.copy()
    latest = df.iloc[-1]
    close = latest["Close"]

    df["TR"] = calc_tr(df)
    df["N"] = df["TR"].ewm(span=20, adjust=False).mean()

    n_value = df.iloc[-1]["N"]
    n_ratio = n_value / close if close > 0 and pd.notna(n_value) else None

    df["value_krw"] = df["Close"] * df["Volume"]
    value_krw_20d_avg = df["value_krw"].tail(20).mean()

    listed_years = (df.index[-1] - df.index[0]).days / 365.25

    c1_price_ok = PARAMS["price_min"] <= close <= PARAMS["price_max"]
    c1_nratio_ok = n_ratio is not None and PARAMS["nratio_min"] <= n_ratio <= PARAMS["nratio_max"]
    c1_value_ok = value_krw_20d_avg >= PARAMS["value_krw_20d_min"]
    c1_listed_ok = listed_years >= PARAMS["listed_years_min"]

    return {
        "close": close,
        "N": n_value,
        "N_ratio": n_ratio,
        "value_krw_20d_avg": value_krw_20d_avg,
        "listed_years": listed_years,
        "C1_PASS": all([c1_price_ok, c1_nratio_ok, c1_value_ok, c1_listed_ok]),
    }


def detect_turtle_signal(df):
    df = df.copy()
    df["HH55"] = df["High"].rolling(55).max().shift(1)
    latest = df.iloc[-1]

    if pd.isna(latest["HH55"]):
        return None

    if latest["Close"] <= latest["HH55"]:
        return None

    return {
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "close": latest["Close"],
        "hh55": latest["HH55"],
    }


def find_long_entry_signals():
    stocks = get_stocks()
    signals = []
    errors = []
    step1_pass_count = 0

    for _, row in stocks.iterrows():
        code = row["Code"]
        name = row["Name"]

        try:
            df = get_price_data(code)
            if df is None:
                continue

            step1 = evaluate_step1(df)
            if not step1["C1_PASS"]:
                continue

            step1_pass_count += 1
            signal = detect_turtle_signal(df)

            if signal:
                signals.append({
                    "code": code,
                    "name": name,
                    "date": signal["date"],
                    "close": signal["close"],
                    "hh55": signal["hh55"],
                    "N": step1["N"],
                    "N_ratio": step1["N_ratio"],
                    "value_krw_20d_avg": step1["value_krw_20d_avg"],
                    "tv_link": f"https://kr.tradingview.com/chart/?symbol=KRX:{code}",
                })

            time.sleep(0.1)

        except Exception as e:
            errors.append({"code": code, "name": name, "error": str(e)})

    return signals, errors, len(stocks), step1_pass_count


def fmt(value, digits=2):
    return "-" if value is None else f"{value:,.{digits}f}"


def fmt_pct(value):
    return "-" if value is None else f"{value * 100:.2f}%"


def fmt_100m(value):
    return "-" if value is None else f"{value / 100_000_000:,.1f}억"


def fmt_elapsed(seconds):
    minutes = int(seconds // 60)
    remain_seconds = int(seconds % 60)
    return f"{minutes}분 {remain_seconds}초" if minutes > 0 else f"{remain_seconds}초"


def send_email(signals, errors, total_count, step1_pass_count, latest_market_date, elapsed_seconds):
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    if signals:
        subject = f"🟢 [{MARKET} Turtle] {latest_market_date} Long Entry {len(signals)}건"
    else:
        subject = f"⚪ [{MARKET} Turtle] {latest_market_date} No Signal"

    rows = "".join(
        f"""
        <tr>
          <td>{s["code"]}</td>
          <td>{s["name"]}</td>
          <td>{s["date"]}</td>
          <td style="text-align:right;">{fmt(s["close"])}</td>
          <td style="text-align:right;">{fmt(s["hh55"])}</td>
          <td style="text-align:right;">{fmt(s["N"])}</td>
          <td style="text-align:right;">{fmt_pct(s["N_ratio"])}</td>
          <td style="text-align:right;">{fmt_100m(s["value_krw_20d_avg"])}</td>
          <td><a href="{s["tv_link"]}">차트 보기</a></td>
        </tr>
        """
        for s in signals
    ) if signals else """
        <tr>
          <td colspan="9" style="text-align:center;">오늘 발생한 Long Entry 신호 없음</td>
        </tr>
    """

    error_text = f"<p style='color:#999;'>일부 종목 조회 실패: {len(errors)}건</p>" if errors else ""

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
      <h2>📈 {MARKET} Turtle Long Entry Report</h2>

      <p><b>실행 시각:</b> {run_date}</p>
      <p><b>기준 거래일:</b> {latest_market_date}</p>
      <p><b>전체 검사 종목 수:</b> {total_count}</p>
      <p><b>Step1 통과 종목 수:</b> {step1_pass_count}</p>
      <p><b>Long Entry 발생:</b> {len(signals)}건</p>
      <p><b>총 소요시간:</b> {fmt_elapsed(elapsed_seconds)}</p>
      <p><b>평균 처리시간:</b> {elapsed_seconds / max(total_count, 1):.2f}초/종목</p>

      <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
        <tr style="background-color:#f2f2f2;">
          <th>종목코드</th>
          <th>종목명</th>
          <th>기준일</th>
          <th>종가</th>
          <th>직전 55일 고가</th>
          <th>N</th>
          <th>N_ratio</th>
          <th>20일 평균 거래대금</th>
          <th>TradingView</th>
        </tr>
        {rows}
      </table>

      {error_text}

      <p style="color:gray;">GitHub Actions + FinanceDataReader 자동 발송</p>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)


if __name__ == "__main__":
    start_time = time.time()
    latest_market_date = get_latest_market_date()

    if not is_today_market_data(latest_market_date):
        print(f"오늘 장 데이터 없음. latest_market_date={latest_market_date}")
    else:
        signals, errors, total_count, step1_pass_count = find_long_entry_signals()
        elapsed_seconds = time.time() - start_time
        send_email(signals, errors, total_count, step1_pass_count, latest_market_date, elapsed_seconds)
