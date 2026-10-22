"""One Gmail connection reused for a whole batch (instead of login-per-email)."""
import smtplib
import ssl
from contextlib import contextmanager
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import streamlit as st

RECONNECT_EVERY = 100   # refresh the connection every N emails


class _Mailer:
    def __init__(self):
        self.sender = st.secrets["EMAIL_ADDRESS"]
        self.password = st.secrets["EMAIL_PASSWORD"]
        self.server = None
        self.count = 0

    def _connect(self):
        self.close()
        s = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(self.sender, self.password)
        self.server, self.count = s, 0

    def close(self):
        if self.server is not None:
            try:
                self.server.quit()
            except Exception:
                pass
            self.server = None

    def send(self, to_email, subject, html, plain):
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"SnapClass <{self.sender}>"
        msg["To"] = to_email
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))

        for attempt in (1, 2):
            try:
                if self.server is None or self.count >= RECONNECT_EVERY:
                    self._connect()
                self.server.sendmail(self.sender, to_email, msg.as_string())
                self.count += 1
                return
            except (smtplib.SMTPServerDisconnected, ConnectionError,
                    TimeoutError, ssl.SSLError):
                self.close()          # dropped connection: reconnect once, then give up
                if attempt == 2:
                    raise


@contextmanager
def pooled_smtp():
    """Inside this block every email goes through ONE reused connection."""
    import src.services.email_service as es
    import src.services.weekly_report_service as wrs

    mailer = _Mailer()
    orig_es, orig_wrs = es._send, wrs._send
    es._send = wrs._send = mailer.send
    try:
        yield mailer
    finally:
        es._send, wrs._send = orig_es, orig_wrs
        mailer.close()
