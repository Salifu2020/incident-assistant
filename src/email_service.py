"""
Email service for sending password reset emails and notifications.
"""
import os
import smtplib
import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from typing import Optional
import logging
from jinja2 import Template

logger = logging.getLogger(__name__)

# Email configuration from environment variables
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", SMTP_USER)
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Incident Assistant")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

# App URL for reset links
APP_URL = os.environ.get("APP_URL", "http://localhost:8501")


def get_reset_email_template() -> str:
    """Get HTML email template for password reset."""
    return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }
        .container {
            background-color: #f9fafb;
            border-radius: 10px;
            padding: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        .logo {
            font-size: 32px;
            margin-bottom: 10px;
        }
        h1 {
            color: #667eea;
            margin: 0;
        }
        .content {
            background-color: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        .button {
            display: inline-block;
            padding: 12px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-weight: bold;
            margin: 20px 0;
        }
        .button:hover {
            opacity: 0.9;
        }
        .token-box {
            background-color: #f3f4f6;
            border: 2px dashed #667eea;
            padding: 15px;
            border-radius: 6px;
            text-align: center;
            font-family: monospace;
            font-size: 18px;
            font-weight: bold;
            color: #667eea;
            margin: 20px 0;
            word-break: break-all;
        }
        .footer {
            text-align: center;
            color: #6b7280;
            font-size: 12px;
            margin-top: 30px;
        }
        .warning {
            background-color: #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .info {
            background-color: #dbeafe;
            border-left: 4px solid #3b82f6;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">📚</div>
            <h1>Password Reset Request</h1>
        </div>
        
        <div class="content">
            <p>Hello,</p>
            
            <p>We received a request to reset your password for your <strong>Incident Assistant</strong> account.</p>
            
            <p>Click the button below to reset your password:</p>
            
            <div style="text-align: center;">
                <a href="{{ reset_url }}" class="button">Reset Password</a>
            </div>
            
            <p>Or copy and paste this link into your browser:</p>
            <div class="token-box">{{ reset_url }}</div>
            
            <div class="warning">
                <strong>⚠️ Important:</strong> This link will expire in <strong>30 minutes</strong> and can only be used once.
            </div>
            
            <div class="info">
                <strong>ℹ️ Didn't request this?</strong> If you didn't request a password reset, you can safely ignore this email. Your password will not be changed.
            </div>
            
            <p>If the button doesn't work, you can also use this reset token:</p>
            <div class="token-box">{{ reset_token }}</div>
        </div>
        
        <div class="footer">
            <p>This is an automated message. Please do not reply to this email.</p>
            <p>&copy; {{ year }} Incident Assistant. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""


def get_reset_email_text_template() -> str:
    """Get plain text email template for password reset."""
    return """
Password Reset Request

Hello,

We received a request to reset your password for your Incident Assistant account.

Reset your password by clicking this link:
{{ reset_url }}

Or use this reset token: {{ reset_token }}

IMPORTANT: This link will expire in 30 minutes and can only be used once.

Didn't request this? If you didn't request a password reset, you can safely ignore this email. Your password will not be changed.

This is an automated message. Please do not reply to this email.

© {{ year }} Incident Assistant. All rights reserved.
"""


class EmailService:
    """Service for sending emails."""
    
    @staticmethod
    def is_configured() -> bool:
        """Check if email service is configured."""
        return bool(SMTP_USER and SMTP_PASSWORD and SMTP_HOST)
    
    @staticmethod
    async def send_password_reset_email(email: str, reset_token: str) -> bool:
        """Send password reset email."""
        if not EmailService.is_configured():
            logger.warning("Email service not configured. Skipping email send.")
            return False
        
        try:
            # Generate reset URL
            reset_url = f"{APP_URL}/?reset_token={reset_token}"
            
            # Render email template
            html_template = Template(get_reset_email_template())
            text_template = Template(get_reset_email_text_template())
            
            from datetime import datetime
            year = datetime.now().year
            
            html_content = html_template.render(
                reset_url=reset_url,
                reset_token=reset_token,
                year=year
            )
            text_content = text_template.render(
                reset_url=reset_url,
                reset_token=reset_token,
                year=year
            )
            
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = "Password Reset Request - Incident Assistant"
            message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM_EMAIL))
            message["To"] = email
            
            # Add both plain text and HTML versions
            part1 = MIMEText(text_content, "plain")
            part2 = MIMEText(html_content, "html")
            
            message.attach(part1)
            message.attach(part2)
            
            # Send email
            if SMTP_USE_TLS:
                await aiosmtplib.send(
                    message,
                    hostname=SMTP_HOST,
                    port=SMTP_PORT,
                    username=SMTP_USER,
                    password=SMTP_PASSWORD,
                    use_tls=True,
                )
            else:
                await aiosmtplib.send(
                    message,
                    hostname=SMTP_HOST,
                    port=SMTP_PORT,
                    username=SMTP_USER,
                    password=SMTP_PASSWORD,
                    use_tls=False,
                )
            
            logger.info(f"Password reset email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send password reset email to {email}: {e}")
            return False
    
    @staticmethod
    def send_password_reset_email_sync(email: str, reset_token: str) -> bool:
        """Send password reset email (synchronous version for non-async contexts)."""
        if not EmailService.is_configured():
            logger.warning("Email service not configured. Skipping email send.")
            return False
        
        try:
            # Generate reset URL
            reset_url = f"{APP_URL}/?reset_token={reset_token}"
            
            # Render email template
            html_template = Template(get_reset_email_template())
            text_template = Template(get_reset_email_text_template())
            
            from datetime import datetime
            year = datetime.now().year
            
            html_content = html_template.render(
                reset_url=reset_url,
                reset_token=reset_token,
                year=year
            )
            text_content = text_template.render(
                reset_url=reset_url,
                reset_token=reset_token,
                year=year
            )
            
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = "Password Reset Request - Incident Assistant"
            message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM_EMAIL))
            message["To"] = email
            
            # Add both plain text and HTML versions
            part1 = MIMEText(text_content, "plain")
            part2 = MIMEText(html_content, "html")
            
            message.attach(part1)
            message.attach(part2)
            
            # Send email synchronously
            if SMTP_USE_TLS:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.send_message(message)
            else:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.send_message(message)
            
            logger.info(f"Password reset email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send password reset email to {email}: {e}")
            return False






