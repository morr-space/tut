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

# 테스트 성공 후 전체 KOSPI로 실행
TEST_MODE = False

TEST_CODES = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "005490",  # POSCO홀딩스
    "035420",  # NAVER
    "005380",  # 현대차
]


def get_latest_market_date():
    end = datetime.now()
    start = end - timedelta(days=10)

    df = fdr.DataReader("KS11", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    if df.empty:
        raise ValueError("KOSPI 지수 데이터를 가져오지 못했습니다.")

    return df.index[-1].strftime("%Y-%m-%d")


def is_today_market_data(latest_market_date):
    today = datetime.now().strftime("%Y-%m-%d")
    return latest_market_date == today


def get_kospi_stocks():
    kospi = fdr.StockListing("KOSPI")
    kospi = kospi[["Code", "Name", "Market"]].copy()

    if TEST_MODE:
        kospi = kospi[kospi["Code"].isin(TEST_CODES)].copy()

    return kospi


def get_price_data(code):
    end = datetime.now()
    start = end - timedelta(days=140)

    df = fdr.DataReader(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    if df.empty or len(df) < 60:
        return None

    return df


def detect_turtle_signal(df):
    df = df.copy()

    # 직전 55거래일 최고가
    df["HH55"] = df["High"].rolling(55).max().shift(1)

    latest = df.iloc[-1]

    if pd.isna(latest["HH55"]):
        return None

    is_long_entry = latest["Close"] > latest["HH55"]

    if not is_long_entry:
        return None

    return {
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "close": latest["Close"],
        "hh55": latest["HH55"],
    }


def find_long_entry_signals():
    stocks = get_kospi_stocks()
    signals = []
    errors = []

    for _, row in stocks.iterrows():
        code = row["Code"]
        name = row["Name"]

        try:
            df = get_price_data(code)

            if df is None:
                continue

            signal = detect_turtle_signal(df)

            if signal:
                tv_link = f"https://kr.tradingview.com/chart/?symbol=KRX:{code}"

                signals.append({
                    "code": code,
                    "name": name,
                    "date": signal["date"],
                    "close": signal["close"],
                    "hh55": signal["hh55"],
                    "tv_link": tv_link,
                })

            # 과도한 호출 방지
            time.sleep(0.2)

        except Exception as e:
            errors.append({
                "code": code,
                "name": name,
                "error": str(e),
            })

    return signals, errors, len(stocks)


def fmt(value, digits=2):
    if value is None:
        return "-"
    return f"{value:,.{digits}f}"


def send_email(signals, errors, total_count, latest_market_date):
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    if signals:
        rows = "".join(
            f"""
            <tr>
              <td>{s["code"]}</td>
              <td>{s["name"]}</td>
              <td>{s["date"]}</td>
              <td style="text-align:right;">{fmt(s["close"])}</td>
              <td style="text-align:right;">{fmt(s["hh55"])}</td>
              <td><a href="{s["tv_link"]}">차트 보기</a></td>
            </tr>
            """
            for s in signals
        )
    else:
        rows = """
        <tr>
          <td colspan="6" style="text-align:center;">오늘 발생한 Long Entry 신호 없음</td>
        </tr>
        """

    error_text = ""
    if errors:
        error_text = f"""
        <p style="color:#999;">
          일부 종목 조회 실패: {len(errors)}건
        </p>
        """

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
      <h2>📈 Turtle Long Entry Report</h2>

      <p><b>실행 시각:</b> {run_date}</p>
      <p><b>기준 거래일:</b> {latest_market_date}</p>
      <p><b>검사 종목 수:</b> {total_count}</p>
      <p><b>Long Entry 발생:</b> {len(signals)}건</p>

      <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
        <tr style="background-color:#f2f2f2;">
          <th>종목코드</th>
          <th>종목명</th>
          <th>기준일</th>
          <th>종가</th>
          <th>직전 55일 고가</th>
          <th>TradingView</th>
        </tr>
        {rows}
      </table>

      {error_text}

      <p style="color:gray;">GitHub Actions + FinanceDataReader 자동 발송</p>
    </body>
    </html>
    """

    subject = f"[Turtle] {latest_market_date} Long Entry {len(signals)}건"

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
    latest_market_date = get_latest_market_date()

    if not is_today_market_data(latest_market_date):
        print(f"오늘 장 데이터 없음. latest_market_date={latest_market_date}")
    else:
        signals, errors, total_count = find_long_entry_signals()
        send_email(signals, errors, total_count, latest_market_date)
