import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Configuration ─────────────────────────────────────────────────────────────
# Set these as environment variables on Render (never hard-code credentials).
# On Render dashboard: Settings → Environment → Add Environment Variable
#   SMTP_USER  →  your Gmail address  (e.g. yourshop@gmail.com)
#   SMTP_PASS  →  your 16-char Google App Password (NOT your normal password)
#
# To create a Google App Password:
#   Google Account → Security → 2-Step Verification → App passwords → Mail
#
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASS: str = os.getenv("SMTP_PASS", "")
SMTP_HOST: str = "smtp.gmail.com"
# Changed to 465 for implicit SSL to bypass cloud egress firewalls
SMTP_PORT: int = 465


# ── HTML email template ───────────────────────────────────────────────────────
def _build_html(
    customer_name: str,
    order_id: int,
    amount_paid: float,
    balance_due: float,
    is_fully_paid: bool,
) -> str:
    """Return a styled HTML string for the confirmation email."""

    balance_row = ""
    if not is_fully_paid:
        balance_row = f"""
        <tr>
          <td style="padding:8px 0;color:#555;font-size:14px;">Balance Remaining:</td>
          <td style="padding:8px 0;font-weight:700;color:#c0392b;
                     text-align:right;font-size:14px;">${balance_due:.2f}</td>
        </tr>"""

    partial_notice = ""
    if not is_fully_paid:
        partial_notice = f"""
        <div style="background:#fff8e1;border-left:4px solid #f59e0b;
                    border-radius:6px;padding:14px 18px;margin:20px 0;">
          <strong style="color:#92400e;">⚠️ Partial Payment Recorded</strong><br>
          <span style="font-size:13px;color:#78350f;">
            A balance of <strong>${balance_due:.2f}</strong> remains on this order.
            It has been added to your account ledger and will be due before shipment.
          </span>
        </div>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#e7ecef;
             font-family:'Helvetica Neue',Arial,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#e7ecef;padding:36px 0;">
    <tr><td align="center">

      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:14px;
                    overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.09);">

        <tr>
          <td style="background:#274c77;padding:32px 44px;text-align:center;">
            <h1 style="color:#ffffff;margin:0;font-size:26px;
                       letter-spacing:1px;font-weight:800;">B2B APPAREL</h1>
            <p  style="color:#b8cce0;margin:7px 0 0;font-size:13px;">
              Wholesale Clothing Platform
            </p>
          </td>
        </tr>

        <tr>
          <td style="padding:40px 44px;">

            <h2 style="color:#274c77;margin:0 0 10px;font-size:22px;">
              Order Confirmed! 🎉
            </h2>
            <p style="color:#555;font-size:15px;margin:0 0 24px;">
              Hi <strong>{customer_name}</strong>, your B2B order has been
              successfully placed and is now being processed.
            </p>

            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f0f4f8;border-radius:10px;
                          padding:20px 24px;margin-bottom:20px;">
              <tr>
                <td style="padding:8px 0;color:#555;font-size:14px;">
                  Order Number:
                </td>
                <td style="padding:8px 0;font-weight:700;color:#274c77;
                           text-align:right;font-size:14px;">
                  #{order_id:05d}
                </td>
              </tr>
              <tr>
                <td style="padding:8px 0;color:#555;font-size:14px;">
                  Amount Paid Today:
                </td>
                <td style="padding:8px 0;font-weight:700;color:#166534;
                           text-align:right;font-size:14px;">
                  ${amount_paid:.2f}
                </td>
              </tr>
              {balance_row}
            </table>

            {partial_notice}

            <p style="color:#555;font-size:14px;margin:0 0 8px;">
              📎 Your invoice is attached to this email as a PDF — please keep
              it for your records.
            </p>
            <p style="color:#888;font-size:13px;margin:0 0 30px;">
              Questions? Reply to this email or reach us at
              <a href="mailto:support@b2bapparel.com"
                 style="color:#274c77;">support@b2bapparel.com</a>.
            </p>

            <p style="color:#555;font-size:14px;margin:0;">
              Thank you for choosing B2B Apparel!
            </p>

          </td>
        </tr>

        <tr>
          <td style="background:#274c77;padding:18px 44px;text-align:center;">
            <p style="color:#b8cce0;font-size:11px;margin:0;">
              © 2025 B2B Apparel · All rights reserved ·
              <a href="mailto:support@b2bapparel.com"
                 style="color:#b8cce0;">support@b2bapparel.com</a>
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>

</body>
</html>
"""


# ── Public function ───────────────────────────────────────────────────────────
def send_order_confirmation(
    to_email: str,
    customer_name: str,
    order_id: int,
    amount_paid: float,
    balance_due: float,
    is_fully_paid: bool,
    pdf_path: str,
) -> None:
    """
    Send an HTML order-confirmation email with the invoice PDF attached.

    Parameters
    ----------
    to_email       : recipient's email address
    customer_name  : displayed in the greeting
    order_id       : used in subject line and order-number display
    amount_paid    : shown in the summary box
    balance_due    : shown only when is_fully_paid is False
    is_fully_paid  : controls whether the partial-payment notice appears
    pdf_path       : absolute path to the generated invoice PDF
    """
    if not SMTP_USER or not SMTP_PASS:
        # Fail loudly in development so you notice the missing env vars
        raise EnvironmentError(
            "SMTP_USER and SMTP_PASS environment variables must be set."
        )

    subject = (
        f"✅ Order Confirmed – B2B Apparel #{order_id:05d}"
        if is_fully_paid
        else f"🧾 Order #{order_id:05d} Received – Balance Remaining"
    )

    msg = MIMEMultipart("alternative")
    msg["From"]    = SMTP_USER
    msg["To"]      = to_email
    msg["Subject"] = subject

    html_body = _build_html(
        customer_name=customer_name,
        order_id=order_id,
        amount_paid=amount_paid,
        balance_due=balance_due,
        is_fully_paid=is_fully_paid,
    )
    msg.attach(MIMEText(html_body, "html"))

    # ── Attach the PDF ────────────────────────────────────────────────────────
    with open(pdf_path, "rb") as fh:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(fh.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="B2BApparel_Invoice_{order_id:05d}.pdf"',
        )
        msg.attach(part)

    # ── Send ──────────────────────────────────────────────────────────────────
    # Switched to SMTP_SSL to ensure Render routes the traffic correctly
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)