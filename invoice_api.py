import os
import smtplib
from datetime import datetime
from typing import List
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, EmailStr
from fpdf import FPDF
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

app = FastAPI()

# --- CONFIGURATION (Update these) ---
SMTP_USER = "your-email@gmail.com"
SMTP_PASS = "xxxx xxxx xxxx xxxx" # Your 16-char Google App Password

# --- MODELS ---
class Item(BaseModel):
    name: str
    quantity: int
    price: float

class OrderData(BaseModel):
    orderId: str
    customerName: str
    email: EmailStr
    streetAddress: str
    city: str
    country: str
    postalCode: str
    items: List[Item]
    totalDue: float

# --- LOGIC ---
def process_invoice(order: OrderData):
    # 1. Create PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 20)
    pdf.set_text_color(39, 76, 119) # Majesty Blue
    pdf.cell(0, 10, "INVOICE", ln=True, align='R')
    
    pdf.set_font("Helvetica", size=10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 5, f"Invoice #: {order.orderId}", ln=True, align='R')
    pdf.cell(0, 5, f"Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True, align='R')
    pdf.ln(10)

    # Bill To
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 6, f"Bill To: {order.customerName}", ln=True)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 5, order.streetAddress, ln=True)
    pdf.cell(0, 5, f"{order.city}, {order.country} {order.postalCode}", ln=True)
    pdf.ln(10)

    # Table Header
    pdf.set_fill_color(39, 76, 119)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(90, 10, " Item", border=1, fill=True)
    pdf.cell(20, 10, " Qty", border=1, fill=True, align='C')
    pdf.cell(40, 10, " Price", border=1, fill=True, align='C')
    pdf.cell(40, 10, " Total", border=1, fill=True, align='C')
    pdf.ln()

    # Rows
    pdf.set_text_color(0, 0, 0)
    for item in order.items:
        pdf.cell(90, 10, f" {item.name}", border=1)
        pdf.cell(20, 10, f" {item.quantity}", border=1, align='C')
        pdf.cell(40, 10, f" ${item.price:.2f}", border=1, align='C')
        pdf.cell(40, 10, f" ${(item.quantity * item.price):.2f}", border=1, align='C')
        pdf.ln()

    pdf.ln(5)
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(150, 10, "Total Due: ", align='R')
    pdf.cell(40, 10, f"${order.totalDue:.2f}", align='C')

    pdf_file = f"Invoice_{order.orderId}.pdf"
    pdf.output(pdf_file)

    # 2. Send Email
    msg = MIMEMultipart()
    msg['From'], msg['To'], msg['Subject'] = SMTP_USER, order.email, f"Invoice #{order.orderId}"
    msg.attach(MIMEText(f"Hi {order.customerName}, thanks for your order! Invoice attached.", 'plain'))

    with open(pdf_file, "rb") as f:
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename={pdf_file}")
        msg.attach(part)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)

    os.remove(pdf_file) # Clean up

# --- ENDPOINT ---
@app.post("/api/checkout-success")
async def checkout_success(order: OrderData, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_invoice, order)
    return {"status": "success"}