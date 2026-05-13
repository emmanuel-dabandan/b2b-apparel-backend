import os
import tempfile
from datetime import datetime
from dataclasses import dataclass
from typing import List
from fpdf import FPDF

# ── Brand palette ─────────────────────────────────────────────────────────────
PRIMARY      = (39,  76,  119)   # #274c77
LIGHT_BG     = (231, 236, 239)   # #e7ecef
WHITE        = (255, 255, 255)
INK          = (22,  43,  68)    # #162b44
MUTED        = (110, 125, 145)
GREEN        = (34,  139,  34)
AMBER        = (180, 105,   0)
RED          = (200,  53,  69)


# ── Data contracts (plain dataclasses — no Pydantic needed here) ──────────────
@dataclass
class InvoiceItem:
    name: str
    quantity: int
    price: float          # unit price at purchase

@dataclass
class InvoiceData:
    order_id:       int
    customer_name:  str
    customer_email: str
    items:          List[InvoiceItem]
    subtotal:       float   # after bulk discount, before tax/shipping
    tax_amount:     float   # 6.5 % of subtotal
    shipping_cost:  float   # 0 / 30 / 90
    total_due:      float   # subtotal + tax + shipping
    amount_paid:    float
    balance_due:    float
    payment_status: str


# ── Internal helpers ──────────────────────────────────────────────────────────
def _set_color(pdf: FPDF, rgb: tuple):
    """Set both draw and text color together."""
    pdf.set_text_color(*rgb)


def _header_band(pdf: FPDF):
    """Full-width primary-blue header with company name + INVOICE label."""
    pdf.set_fill_color(*PRIMARY)
    pdf.rect(0, 0, 210, 42, "F")

    # Company name (left)
    pdf.set_xy(12, 11)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*WHITE)
    pdf.cell(90, 11, "B2B APPAREL")

    # INVOICE (right)
    pdf.set_xy(0, 9)
    pdf.set_font("Helvetica", "B", 30)
    pdf.cell(198, 14, "INVOICE", align="R")

    # Tagline
    pdf.set_xy(12, 27)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(180, 200, 220)
    pdf.cell(0, 5, "Wholesale Clothing Platform  |  support@b2bapparel.com")


def _meta_block(pdf: FPDF, data: InvoiceData):
    """Two-column block: BILL TO (left) and invoice details (right)."""
    top_y = 50

    # ── Left: Bill To ──────────────────────────────────────────────
    pdf.set_xy(12, top_y)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(0, 5, "BILL TO")

    pdf.set_xy(12, top_y + 6)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*INK)
    pdf.cell(0, 6, data.customer_name)

    pdf.set_xy(12, top_y + 13)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, data.customer_email)

    # ── Right: Invoice meta ────────────────────────────────────────
    lx = 128

    def meta_row(label: str, value: str, vc=None):
        cy = pdf.get_y()
        pdf.set_x(lx)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*MUTED)
        pdf.cell(40, 6, label, align="R")
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_text_color(*(vc or INK))
        pdf.cell(30, 6, value, align="R", ln=True)

    pdf.set_xy(lx, top_y)
    meta_row("Invoice No:", f"#{data.order_id:05d}")
    meta_row("Date:", datetime.now().strftime("%B %d, %Y"))
    sc = GREEN if data.balance_due == 0 else AMBER
    meta_row("Status:", data.payment_status, vc=sc)

    pdf.ln(6)


def _items_table(pdf: FPDF, data: InvoiceData):
    """Striped items table."""
    col = [93, 20, 37, 38]   # description | qty | unit price | line total

    # Table header
    pdf.set_x(12)
    pdf.set_fill_color(*PRIMARY)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(col[0], 9, "  ITEM DESCRIPTION", fill=True)
    pdf.cell(col[1], 9, "QTY",        fill=True, align="C")
    pdf.cell(col[2], 9, "UNIT PRICE", fill=True, align="C")
    pdf.cell(col[3], 9, "TOTAL",      fill=True, align="R")
    pdf.ln()

    # Rows (alternating stripe)
    pdf.set_font("Helvetica", "", 8.5)
    for i, item in enumerate(data.items):
        pdf.set_fill_color(*(LIGHT_BG if i % 2 == 0 else WHITE))
        pdf.set_text_color(*INK)
        pdf.set_x(12)

        name = item.name if len(item.name) <= 54 else item.name[:51] + "..."
        pdf.cell(col[0], 8, f"  {name}", fill=True)
        pdf.cell(col[1], 8, str(item.quantity),              fill=True, align="C")
        pdf.cell(col[2], 8, f"${item.price:.2f}",            fill=True, align="C")
        pdf.cell(col[3], 8, f"${item.quantity * item.price:.2f}", fill=True, align="R")
        pdf.ln()

    pdf.ln(5)

    # Hairline divider
    pdf.set_draw_color(*PRIMARY)
    pdf.set_line_width(0.35)
    pdf.line(12, pdf.get_y(), 198, pdf.get_y())
    pdf.ln(4)


def _totals_block(pdf: FPDF, data: InvoiceData):
    """Right-aligned totals with highlighted grand-total row."""
    lx = 128  # label column x

    def trow(label: str, value: float, bold=False, color=None):
        pdf.set_x(lx)
        font_style = "B" if bold else ""
        pdf.set_font("Helvetica", font_style, 9)
        pdf.set_text_color(*(color or MUTED))
        pdf.cell(42, 6.5, label, align="R")
        pdf.set_text_color(*(color or INK))
        pdf.cell(28, 6.5, f"${value:.2f}", align="R", ln=True)

    trow("Subtotal:", data.subtotal)
    trow("Tax (6.5%):", data.tax_amount)

    shipping_labels = {0: "Shipping (Standard - Free):", 30: "Shipping (Express):", 90: "Shipping (Same Day):"}
    trow(shipping_labels.get(int(data.shipping_cost), "Shipping:"), data.shipping_cost)

    pdf.ln(2)

    # Total-due highlighted band
    pdf.set_x(lx)
    pdf.set_fill_color(*PRIMARY)
    pdf.set_text_color(*WHITE)
    pdf.set_font("Helvetica", "B", 11)
    total_label = "TOTAL DUE:"
    pdf.cell(42, 11, total_label, fill=True, align="R")
    pdf.cell(28, 11, f"${data.total_due:.2f}", fill=True, align="R", ln=True)

    pdf.ln(3)
    trow("Amount Paid:", data.amount_paid, bold=True, color=GREEN)

    if data.balance_due > 0:
        trow("Balance Due:", data.balance_due, bold=True, color=RED)


def _partial_notice(pdf: FPDF, data: InvoiceData):
    """Amber notice box shown only on partial-payment invoices."""
    if data.balance_due <= 0:
        return
    pdf.ln(6)
    pdf.set_x(12)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*AMBER)
    pdf.cell(
        186, 5.5,
        f"  Partial Payment Notice: A balance of ${data.balance_due:.2f} remains on this order.",
        ln=True,
    )
    pdf.set_x(12)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(186, 5, "  Please refer to your account ledger for the full payment schedule.", ln=True)


def _footer(pdf: FPDF):
    """Fixed footer at the bottom of the page."""
    pdf.set_y(-18)
    pdf.set_draw_color(*PRIMARY)
    pdf.set_line_width(0.3)
    pdf.line(12, pdf.get_y() - 2, 198, pdf.get_y() - 2)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(
        0, 5,
        "Thank you for your business!  |  B2B Apparel  |  support@b2bapparel.com  |  This is a system-generated invoice.",
        align="C",
    )


# ── Public API ────────────────────────────────────────────────────────────────
def generate_invoice_pdf(data: InvoiceData) -> str:
    """
    Build the invoice PDF and return its file path.
    The file is written to the system temp directory and should be deleted
    by the caller after the email has been sent.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)

    _header_band(pdf)
    _meta_block(pdf, data)
    _items_table(pdf, data)
    _totals_block(pdf, data)
    _partial_notice(pdf, data)
    _footer(pdf)

    path = os.path.join(tempfile.gettempdir(), f"invoice_{data.order_id}.pdf")
    pdf.output(path)
    return path