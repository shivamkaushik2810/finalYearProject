"""One SMTP connection reused for a whole batch (instead of login-per-email)."""
import smtplib
import ssl
from contextlib import contextmanager
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from src.services.smtp_config import open_smtp

RECONNECT_EVERY = 100   # refresh the connection every N emails


class _Mailer:
    def __init__(self):
        self.server = None
        self.cfg = None
        self.count = 0

    def _connect(self):
        self.close()
        self.server, self.cfg = open_smtp()
        self.count = 0

    def close(self):
        if self.server is not None:
            try:
                self.server.quit()
            except Exception:
                pass
            self.server = None

    def send(self, to_email, subject, html, plain):
        for attempt in (1, 2):
            try:
                if self.server is None or self.count >= RECONNECT_EVERY:
                    self._connect()
                sender = self.cfg["sender"]
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = f"SnapClass <{sender}>"
                msg["To"] = to_email
                msg.attach(MIMEText(plain, "plain"))
                msg.attach(MIMEText(html, "html"))
                self.server.sendmail(sender, to_email, msg.as_string())
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
