# Placeholder SMTP sender (wire your provider of choice)
import smtplib
from email.message import EmailMessage

def send_email(to_email: str, subject: str, body: str):
    msg = EmailMessage()
    msg['To'] = to_email
    msg['From'] = "noreply@example.com"
    msg['Subject'] = subject
    msg.set_content(body)
    # Configure SMTP in production; this is a stub.
    # with smtplib.SMTP('localhost') as s:
    #     s.send_message(msg)
    return True
