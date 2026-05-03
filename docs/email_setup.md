# Email Setup

Sandy-Trading-AI supports two email modes.

## Local Preview With Mailpit

Mailpit is an open-source local SMTP preview inbox. It is useful for testing summaries without sending private trading data outside your machine.

```powershell
docker compose up -d mailpit
```

Open:

```text
http://127.0.0.1:8025
```

Use these `.env` values:

```text
ENABLE_EMAIL_SUMMARY=true
EMAIL_SMTP_HOST=localhost
EMAIL_SMTP_PORT=1025
EMAIL_SMTP_USE_TLS=false
EMAIL_SMTP_REQUIRE_AUTH=false
EMAIL_USERNAME=
EMAIL_PASSWORD=
EMAIL_TO=<your email address>
```

Then run:

```powershell
.\scripts\daily_summary.ps1 -SendEmail
```

The message appears in Mailpit. It will not reach Gmail.

## Real External Email

To deliver to Gmail or another inbox, configure a real SMTP account. For Gmail this usually means a Google account with 2-step verification and an app password. For a dedicated provider, use its SMTP host, port, username, and password.

Use:

```text
ENABLE_EMAIL_SUMMARY=true
EMAIL_SMTP_HOST=<smtp host>
EMAIL_SMTP_PORT=<smtp port>
EMAIL_SMTP_USE_TLS=true
EMAIL_SMTP_REQUIRE_AUTH=true
EMAIL_USERNAME=<smtp username>
EMAIL_PASSWORD=<smtp password or app password>
EMAIL_TO=<recipient>
```

Do not commit `.env`.

## Why Not Self-Host Outbound Email Immediately

Running your own outbound SMTP server that reliably reaches Gmail requires a domain, DNS, SPF, DKIM, DMARC, reverse DNS, IP reputation, and monitoring. Without that, messages are commonly blocked or spam-foldered. Mailpit is the safer open-source local preview step; a real SMTP relay is the practical route for external delivery.
