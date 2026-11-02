"""
ResolveAIV2 — Email Notification Service
Handles sending confirmation and security emails (e.g. forgot password, password changed).
Supports SMTP transport in production and in-memory test/dev tracking.
"""

import asyncio
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html
import logging
import smtplib
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


def build_account_confirmation_email(
    to_email: str,
    user_name: str,
    login_url: str,
) -> tuple[str, str, str]:
    """
    Constructs the subject, HTML, and plain-text content for the account creation confirmation email.
    """
    safe_name = html.escape(user_name or "there")
    safe_email = html.escape(to_email)
    safe_url = html.escape(login_url)
    subject = "Confirm Your Account Creation — Welcome to ResolveAI"
    current_year = datetime.now(timezone.utc).year

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #080a08;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #d2dcd0;
      -webkit-font-smoothing: antialiased;
    }}
    .wrapper {{
      width: 100%;
      background-color: #080a08;
      padding: 40px 16px;
      box-sizing: border-box;
    }}
    .card {{
      max-width: 580px;
      margin: 0 auto;
      background-color: #111411;
      border-radius: 16px;
      border: 1px solid #30382c;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
      overflow: hidden;
    }}
    .header {{
      background: #161a16;
      border-bottom: 2px solid #a7fe08;
      padding: 30px 32px 26px;
      text-align: center;
    }}
    .brand {{
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.03em;
      color: #ffffff;
      margin: 0;
    }}
    .brand-accent {{
      color: #a7fe08;
    }}
    .header p {{
      margin: 6px 0 0;
      font-size: 12px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: #8b9b8b;
    }}
    .content {{
      padding: 36px 32px 28px;
    }}
    .greeting {{
      font-size: 18px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 14px;
    }}
    .message {{
      font-size: 14px;
      line-height: 1.6;
      color: #d2dcd0;
      margin: 0 0 20px;
    }}
    .info-card {{
      background-color: #181c18;
      border: 1px solid #30382c;
      border-radius: 12px;
      padding: 18px 20px;
      margin: 22px 0;
    }}
    .info-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 13px;
      color: #d2dcd0;
      margin-bottom: 10px;
    }}
    .info-row:last-child {{
      margin-bottom: 0;
    }}
    .badge {{
      display: inline-block;
      background-color: #1a2216;
      border: 1px solid #30382c;
      color: #a7fe08;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
    }}
    .btn-container {{
      text-align: center;
      margin: 30px 0 28px;
    }}
    .btn {{
      display: inline-block;
      background-color: #a7fe08;
      color: #10130a !important;
      text-decoration: none;
      padding: 14px 34px;
      font-size: 14px;
      font-weight: 700;
      border-radius: 9999px;
      box-shadow: 0 4px 20px rgba(167, 254, 8, 0.25);
    }}
    .fallback {{
      font-size: 12px;
      line-height: 1.5;
      color: #8b9b8b;
      background-color: #181c18;
      border: 1px solid #30382c;
      border-radius: 8px;
      padding: 14px;
      word-break: break-all;
      margin-bottom: 24px;
    }}
    .fallback a {{
      color: #a7fe08;
      text-decoration: underline;
    }}
    .security-notice {{
      border-top: 1px solid #232921;
      padding-top: 20px;
      font-size: 12px;
      color: #8b9b8b;
      line-height: 1.6;
    }}
    .footer {{
      background-color: #161a16;
      border-top: 1px solid #30382c;
      padding: 20px 32px;
      text-align: center;
      font-size: 12px;
      color: #8b9b8b;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="card">
      <div class="header">
        <h1 class="brand">Resolve<span class="brand-accent">AI</span></h1>
        <p>Autonomous Multilingual Customer Support</p>
      </div>
      <div class="content">
        <div class="greeting">Welcome to ResolveAI, {safe_name}!</div>
        <p class="message">
          Your customer account associated with <strong>{safe_email}</strong> has been created and confirmed.
          You're ready to experience 24/7 intelligent voice and chat resolution across English, Tanglish, and Hinglish.
        </p>

        <div class="info-card">
          <div class="info-row">
            <span class="badge">Account Email</span>
            <span><strong>{safe_email}</strong></span>
          </div>
          <div class="info-row">
            <span class="badge">Support Channels</span>
            <span>Web Voice Calls &amp; Realtime Streaming Chat</span>
          </div>
          <div class="info-row">
            <span class="badge">Languages</span>
            <span>English, Tanglish, Hinglish (Multilingual)</span>
          </div>
          <div class="info-row">
            <span class="badge">Status</span>
            <span style="color: #a7fe08; font-weight: 600;">Active &amp; Ready</span>
          </div>
        </div>

        <div class="btn-container">
          <a href="{safe_url}" class="btn" target="_blank" rel="noopener noreferrer">
            Confirm &amp; Access Your Account
          </a>
        </div>

        <div class="fallback">
          Direct link to access your account:<br>
          <a href="{safe_url}">{safe_url}</a>
        </div>

        <div class="security-notice">
          <strong>Security note:</strong><br>
          If you did not register for this ResolveAI account, please contact our support team immediately.
        </div>
      </div>
      <div class="footer">
        &copy; {current_year} ResolveAI. All rights reserved.<br>
        Automated Customer Confirmation Service.
      </div>
    </div>
  </div>
</body>
</html>
"""

    text_content = f"""ResolveAI — Account Creation Confirmation

Welcome to ResolveAI, {user_name or 'there'}!

Your customer account ({to_email}) has been created and confirmed.
You have immediate access to 24/7 AI voice and chat customer resolution.

To access your workspace and sign in:
{login_url}

Account details:
- Email: {to_email}
- Channels: Web Voice & Realtime Streaming Chat
- Languages: English, Tanglish, Hinglish

If you did not create this account, please contact our support team.

© {current_year} ResolveAI. All rights reserved.
"""

    return subject, html_content, text_content


def build_password_reset_email(
    to_email: str,
    user_name: str,
    reset_url: str,
    expires_in_minutes: int = 15,
) -> tuple[str, str, str]:
    """
    Constructs the subject, HTML, and plain-text content for the password reset confirmation email.
    """
    safe_name = html.escape(user_name or "there")
    safe_email = html.escape(to_email)
    safe_url = html.escape(reset_url)
    subject = "Confirm Your Password Reset Request — ResolveAI"
    current_year = datetime.now(timezone.utc).year

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
  <style>
    body {{
      margin: 0;
      padding: 0;
      background-color: #080a08;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #d2dcd0;
      -webkit-font-smoothing: antialiased;
    }}
    .wrapper {{
      width: 100%;
      background-color: #080a08;
      padding: 40px 16px;
      box-sizing: border-box;
    }}
    .card {{
      max-width: 580px;
      margin: 0 auto;
      background-color: #111411;
      border-radius: 16px;
      border: 1px solid #30382c;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
      overflow: hidden;
    }}
    .header {{
      background: #161a16;
      border-bottom: 2px solid #a7fe08;
      padding: 30px 32px 26px;
      text-align: center;
    }}
    .brand {{
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.03em;
      color: #ffffff;
      margin: 0;
    }}
    .brand-accent {{
      color: #a7fe08;
    }}
    .header p {{
      margin: 6px 0 0;
      font-size: 12px;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: #8b9b8b;
    }}
    .content {{
      padding: 36px 32px 28px;
    }}
    .greeting {{
      font-size: 18px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 14px;
    }}
    .message {{
      font-size: 14px;
      line-height: 1.6;
      color: #d2dcd0;
      margin: 0 0 22px;
    }}
    .btn-container {{
      text-align: center;
      margin: 28px 0 28px;
    }}
    .btn {{
      display: inline-block;
      background-color: #a7fe08;
      color: #10130a !important;
      text-decoration: none;
      padding: 14px 34px;
      font-size: 14px;
      font-weight: 700;
      border-radius: 9999px;
      box-shadow: 0 4px 20px rgba(167, 254, 8, 0.25);
    }}
    .expiry-badge {{
      display: inline-block;
      background-color: #1a2216;
      border: 1px solid #30382c;
      color: #a7fe08;
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      margin-bottom: 22px;
    }}
    .fallback {{
      font-size: 12px;
      line-height: 1.5;
      color: #8b9b8b;
      background-color: #181c18;
      border: 1px solid #30382c;
      border-radius: 8px;
      padding: 14px;
      word-break: break-all;
      margin-bottom: 24px;
    }}
    .fallback a {{
      color: #a7fe08;
      text-decoration: underline;
    }}
    .security-notice {{
      border-top: 1px solid #232921;
      padding-top: 20px;
      font-size: 12px;
      color: #8b9b8b;
      line-height: 1.6;
    }}
    .footer {{
      background-color: #161a16;
      border-top: 1px solid #30382c;
      padding: 20px 32px;
      text-align: center;
      font-size: 12px;
      color: #8b9b8b;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="card">
      <div class="header">
        <h1 class="brand">Resolve<span class="brand-accent">AI</span></h1>
        <p>Security &amp; Account Verification</p>
      </div>
      <div class="content">
        <div class="greeting">Hi {safe_name},</div>
        <p class="message">
          We received a request to reset the password for your ResolveAI account associated with <strong>{safe_email}</strong>.
        </p>
        <p class="message">
          Click the button below to confirm this request and choose a new password:
        </p>
        
        <div class="btn-container">
          <a href="{safe_url}" class="btn" target="_blank" rel="noopener noreferrer">
            Confirm &amp; Reset Password
          </a>
        </div>

        <div class="expiry-badge">
          ⏱ This password reset confirmation link will expire in {expires_in_minutes} minutes.
        </div>

        <div class="fallback">
          If the button above does not work, copy and paste this URL into your browser:<br>
          <a href="{safe_url}">{safe_url}</a>
        </div>

        <div class="security-notice">
          <strong>Didn't request this change?</strong><br>
          If you did not initiate this request, you can safely ignore this email. Your password will remain unchanged and your account is secure.
        </div>
      </div>
      <div class="footer">
        &copy; {current_year} ResolveAI. All rights reserved.<br>
        This is an automated security notification. Please do not reply directly to this email.
      </div>
    </div>
  </div>
</body>
</html>
"""

    text_content = f"""ResolveAI — Password Reset Confirmation

Hi {user_name or 'there'},

We received a request to reset the password for your ResolveAI account ({to_email}).

To confirm this request and reset your password, visit the link below:
{reset_url}

NOTE: This confirmation link is valid for {expires_in_minutes} minutes.

If you did not request a password reset, you can safely ignore this email. Your account remains secure and your password will not be changed.

© {current_year} ResolveAI. Automated Security Service.
"""

    return subject, html_content, text_content


def build_password_changed_email(
    to_email: str,
    user_name: str,
) -> tuple[str, str, str]:
    """
    Constructs the confirmation email notifying the user that their password was changed.
    """
    safe_name = html.escape(user_name or "there")
    subject = "Your ResolveAI Password Has Been Successfully Changed"
    current_year = datetime.now(timezone.utc).year
    change_time = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{subject}</title>
  <style>
    body {{
      margin: 0; padding: 0; background-color: #080a08;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      color: #d2dcd0;
    }}
    .wrapper {{ width: 100%; background-color: #080a08; padding: 40px 16px; box-sizing: border-box; }}
    .card {{
      max-width: 580px; margin: 0 auto; background-color: #111411;
      border-radius: 16px; border: 1px solid #30382c;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45); overflow: hidden;
    }}
    .header {{
      background: #161a16; border-bottom: 2px solid #a7fe08;
      padding: 30px 32px 26px; text-align: center;
    }}
    .brand {{ margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.03em; color: #ffffff; }}
    .brand-accent {{ color: #a7fe08; }}
    .header p {{ margin: 6px 0 0; font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: #8b9b8b; }}
    .content {{ padding: 36px 32px 28px; }}
    .greeting {{ font-size: 18px; font-weight: 700; color: #ffffff; margin-bottom: 14px; }}
    .message {{ font-size: 14px; line-height: 1.6; color: #d2dcd0; margin: 0 0 20px; }}
    .success-badge {{
      display: inline-block; background-color: #1a2216; border: 1px solid #30382c;
      color: #a7fe08; padding: 8px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; margin-bottom: 20px;
    }}
    .alert-box {{
      background-color: #241414; border: 1px solid #5a1e1e;
      color: #fca5a5; padding: 14px; border-radius: 8px; font-size: 13px; line-height: 1.5; margin-top: 20px;
    }}
    .footer {{
      background-color: #161a16; border-top: 1px solid #30382c;
      padding: 20px 32px; text-align: center; font-size: 12px; color: #8b9b8b;
    }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="card">
      <div class="header">
        <h1 class="brand">Resolve<span class="brand-accent">AI</span></h1>
        <p>Security Notification</p>
      </div>
      <div class="content">
        <div class="greeting">Hi {safe_name},</div>
        <div class="success-badge">
          ✓ Password successfully updated
        </div>
        <p class="message">
          The password for your ResolveAI account was successfully updated on <strong>{change_time}</strong>.
        </p>
        <p class="message">
          You can now sign in to your ResolveAI account using your newly chosen password.
        </p>
        <div class="alert-box">
          <strong>Didn't make this change?</strong><br>
          If you did not make this change, please contact support or your administrator immediately to secure your account.
        </div>
      </div>
      <div class="footer">
        &copy; {current_year} ResolveAI. All rights reserved.<br>
        Automated Security Notification.
      </div>
    </div>
  </div>
</body>
</html>
"""

    text_content = f"""ResolveAI — Password Change Confirmation

Hi {user_name or 'there'},

The password for your ResolveAI account ({to_email}) was successfully updated on {change_time}.

If you did not make this change, please contact your administrator or support immediately.

© {current_year} ResolveAI.
"""

    return subject, html_content, text_content


class EmailService:
    """
    Central email service for sending transactional & confirmation emails.
    """

    def __init__(self) -> None:
        self.sent_emails: list[dict[str, Any]] = []

    def _send_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> bool:
        """Synchronous SMTP worker function run in a separate thread."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        msg["To"] = to_email

        part1 = MIMEText(text_content, "plain", "utf-8")
        part2 = MIMEText(html_content, "html", "utf-8")
        msg.attach(part1)
        msg.attach(part2)

        try:
            if settings.smtp_ssl:
                server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
                if settings.smtp_tls:
                    server.starttls()

            if settings.smtp_user and settings.smtp_password:
                server.login(settings.smtp_user, settings.smtp_password)

            server.sendmail(settings.smtp_from_email, [to_email], msg.as_string())
            server.quit()
            logger.info("Successfully delivered email to %s via SMTP (%s)", to_email, subject)
            return True
        except Exception as e:
            logger.error("Failed to deliver email to %s via SMTP: %s", to_email, e)
            return False

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
    ) -> dict[str, Any]:
        """
        Sends an email via SMTP if configured and enabled;
        otherwise logs and records the email in memory for dev/test verification.
        """
        is_smtp_configured = bool(settings.email_enabled and settings.smtp_host)
        delivered = False
        delivery_mode = "smtp" if is_smtp_configured else "in_memory_dev"

        if is_smtp_configured:
            delivered = await asyncio.to_thread(
                self._send_smtp, to_email, subject, html_content, text_content
            )
        else:
            # Development / Mock mode
            delivered = True
            logger.info(
                "\n" + "=" * 60 + "\n"
                f"[EMAIL SERVICE — DEV CAPTURE]\n"
                f"To: {to_email}\n"
                f"Subject: {subject}\n"
                f"From: {settings.smtp_from_name} <{settings.smtp_from_email}>\n"
                f"Body Preview:\n{text_content[:300]}...\n"
                + "=" * 60
            )

        record = {
            "to_email": to_email,
            "subject": subject,
            "html_content": html_content,
            "text_content": text_content,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "delivered": delivered,
            "delivery_mode": delivery_mode,
        }
        self.sent_emails.append(record)
        return record

    async def send_account_confirmation_email(
        self,
        to_email: str,
        user_name: str,
        login_url: str | None = None,
    ) -> dict[str, Any]:
        """Send account creation welcome & confirmation email."""
        if not login_url:
            login_url = f"{settings.frontend_url}/login"
        subject, html_content, text_content = build_account_confirmation_email(
            to_email=to_email,
            user_name=user_name,
            login_url=login_url,
        )
        return await self.send_email(to_email, subject, html_content, text_content)

    async def send_password_reset_email(
        self,
        to_email: str,
        user_name: str,
        reset_url: str,
        expires_in_minutes: int = 15,
    ) -> dict[str, Any]:
        """Send password reset confirmation email with reset link."""
        subject, html_content, text_content = build_password_reset_email(
            to_email=to_email,
            user_name=user_name,
            reset_url=reset_url,
            expires_in_minutes=expires_in_minutes,
        )
        return await self.send_email(to_email, subject, html_content, text_content)

    async def send_password_changed_email(
        self,
        to_email: str,
        user_name: str,
    ) -> dict[str, Any]:
        """Send password changed confirmation notification."""
        subject, html_content, text_content = build_password_changed_email(
            to_email=to_email,
            user_name=user_name,
        )
        return await self.send_email(to_email, subject, html_content, text_content)

    def get_last_sent_email(self) -> dict[str, Any] | None:
        """Returns the most recently recorded sent email, or None."""
        return self.sent_emails[-1] if self.sent_emails else None

    def get_sent_emails(self) -> list[dict[str, Any]]:
        """Returns all recorded sent emails."""
        return list(self.sent_emails)

    def clear_sent_emails(self) -> None:
        """Clears all recorded sent emails (useful for test isolation)."""
        self.sent_emails.clear()


# Global singleton instance
email_service = EmailService()
