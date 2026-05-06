import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import FinanceDataReader as fdr


EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]
EMAIL_TO = os.environ.get("EMAIL_TO", EMAIL_USER)


def get_kospi_today():
    # 최근 며칠 데이터를 가져와야 휴장/주말에도 마지막 거래일 데이터를 안전하게 읽을 수 있음
    end = datetime.now()
    start = end - timedelta(days=10)

    df = fdr.DataReader("KS11", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    if df.empty:
        raise ValueError("KOSPI 데이터를 가져오지 못했습니다.")

    latest = df.iloc[-1]
    latest_date = df.index[-1].strftime("%Y-%m-%d")

    prev_close = df.iloc[-2]["Close"] if len(df) >= 2 else None

    change = latest["Close"] - prev_close if prev_close is not None else None
    change_rate = (change / prev_close) * 100 if prev_close else None

    return {
        "date": latest_date,
        "open": latest["Open"],
        "high": latest["High"],
        "low": latest["Low"],
        "close": latest["Close"],
        "volume": latest["Volume"],
        "change": change,
        "change_rate": change_rate,
    }


def format_number(value, digits=2):
    if value is None:
        return "-"
    return f"{value:,.{digits}f}"


def send_email(kospi):
    today = datetime.now().strftime("%Y-%m-%d")

    change_text = (
        "-"
        if kospi["change"] is None
        else f"{kospi['change']:+,.2f} ({kospi['change_rate']:+.2f}%)"
    )

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
      <h2>📈 KOSPI Daily Report</h2>
      <p><b>실행일:</b> {today}</p>
      <p><b>기준 거래일:</b> {kospi["date"]}</p>

      <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
        <tr style="background-color:#f2f2f2;">
          <th>항목</th>
          <th>값</th>
        </tr>
        <tr>
          <td>종가</td>
          <td>{format_number(kospi["close"])}</td>
        </tr>
        <tr>
          <td>전일 대비</td>
          <td>{change_text}</td>
        </tr>
        <tr>
          <td>시가</td>
          <td>{format_number(kospi["open"])}</td>
        </tr>
        <tr>
          <td>고가</td>
          <td>{format_number(kospi["high"])}</td>
        </tr>
        <tr>
          <td>저가</td>
          <td>{format_number(kospi["low"])}</td>
        </tr>
        <tr>
          <td>거래량</td>
          <td>{kospi["volume"]:,.0f}</td>
        </tr>
      </table>

      <br>
      <p style="color:gray;">GitHub Actions + FinanceDataReader 자동 발송</p>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[KOSPI] {kospi['date']} Daily Report"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)


if __name__ == "__main__":
    kospi = get_kospi_today()
    send_email(kospi)