import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASS = os.environ["EMAIL_PASS"]
EMAIL_TO = os.environ["EMAIL_TO"]

def get_turtle_signals():
    return [
        {"code": "005930", "name": "삼성전자", "signal": "LONG_ENTRY"},
        {"code": "005490", "name": "POSCO홀딩스", "signal": "LONG_ENTRY"},
    ]

def send_email(signals):
    today = datetime.now().strftime("%Y-%m-%d")

    rows = ""

    for s in signals:
        rows += f"""
        <tr>
            <td>{s['code']}</td>
            <td>{s['name']}</td>
            <td>{s['signal']}</td>
        </tr>
        """

    html = f"""
    <html>
    <body>
        <h2>📈 Turtle Signal Report ({today})</h2>

        <table border="1" cellpadding="10" cellspacing="0">
            <tr>
                <th>종목코드</th>
                <th>종목명</th>
                <th>시그널</th>
            </tr>

            {rows}

        </table>

        <br>
        <p>GitHub Actions 자동 발송</p>

    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")

    msg["Subject"] = f"[Turtle] {today} Signal Report"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO

    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.send_message(msg)

if __name__ == "__main__":
    signals = get_turtle_signals()
    send_email(signals)