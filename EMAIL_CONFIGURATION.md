# Email Service Configuration

This document explains how to configure the email service for password reset functionality.

## Environment Variables

Set the following environment variables to enable email sending:

### Required Variables

```bash
# SMTP Server Configuration
SMTP_HOST=smtp.gmail.com          # Your SMTP server hostname
SMTP_PORT=587                     # SMTP port (587 for TLS, 465 for SSL)
SMTP_USER=your-email@gmail.com    # Your SMTP username/email
SMTP_PASSWORD=your-app-password   # Your SMTP password or app password
SMTP_FROM_EMAIL=your-email@gmail.com  # From email address
SMTP_FROM_NAME=Incident Assistant     # From name (display name)

# Application URL (for reset links)
APP_URL=http://localhost:8501     # Your application URL

# TLS Configuration
SMTP_USE_TLS=true                 # Use TLS (true/false)
```

## Gmail Configuration

### Using Gmail SMTP:

1. **Enable 2-Step Verification** on your Google account
2. **Generate an App Password**:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a new app password for "Mail"
   - Use this app password as `SMTP_PASSWORD`

3. **Set environment variables:**
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
SMTP_FROM_EMAIL=your-email@gmail.com
SMTP_FROM_NAME=Incident Assistant
SMTP_USE_TLS=true
APP_URL=https://your-domain.com
```

## Other Email Providers

### Outlook/Office 365:
```bash
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=your-email@outlook.com
SMTP_PASSWORD=your-password
SMTP_USE_TLS=true
```

### SendGrid:
```bash
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=your-sendgrid-api-key
SMTP_USE_TLS=true
```

### AWS SES:
```bash
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USER=your-ses-smtp-username
SMTP_PASSWORD=your-ses-smtp-password
SMTP_USE_TLS=true
```

## Development Mode

If email service is not configured, the system will:
- Still generate reset tokens
- Display tokens in the UI (for testing)
- Return tokens in API responses

This allows testing without email configuration.

## Testing Email Configuration

You can test your email configuration by:

1. Setting the environment variables
2. Requesting a password reset
3. Checking your email inbox for the reset email

## Security Notes

- Never commit email credentials to version control
- Use environment variables or secure secret management
- Use app passwords instead of main account passwords when possible
- Enable 2FA on email accounts used for SMTP
- Consider using dedicated email service accounts

## Troubleshooting

### Email not sending:
1. Check SMTP credentials are correct
2. Verify SMTP port and TLS settings
3. Check firewall/network restrictions
4. Review application logs for error messages
5. Test SMTP connection with a simple email client

### Common Errors:
- **Authentication failed**: Check username/password
- **Connection timeout**: Check SMTP host and port
- **TLS error**: Try different TLS settings or port
- **Relay denied**: Some SMTP servers require authentication even for localhost

