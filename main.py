import os
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

import database
from invoice_generator import generate_invoice_pdf, InvoiceData, InvoiceItem
from email_service import send_order_confirmation
from invoice_generator import generate_invoice_pdf, InvoiceData, InvoiceItem
from email_service import send_order_confirmation

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

database.Base.metadata.create_all(bind=database.engine)


@app.on_event("startup")
def seed_inventory():
    db = database.SessionLocal()
    if db.query(database.Product).count() == 0:
        initial_products = [
            database.Product(
                name="Heavyweight Blank Hoodie", base_price=25.00,
                category="Hoodies", image_url="",
                description="Premium 400gsm cotton heavy hoodie.",
                stock=500, sizes="S, M, L, XL", colors="Black, Heather Gray",
            ),
            database.Product(
                name="Premium Cotton Tee", base_price=15.00,
                category="T-Shirts", image_url="",
                description="100% combed ring-spun cotton.",
                stock=1200, sizes="S, M, L, XL, XXL, 3XL",
                colors="White, Black, Navy",
            ),
        ]
        db.add_all(initial_products)
        db.commit()
    db.close()


def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Pydantic models ────────────────────────────────────────────────────────────

class CartItem(BaseModel):
    id: str
    name: str
    basePrice: float
    quantity: int


class CheckoutPayload(BaseModel):
    items:              List[CartItem]
    payment_method:     str            # "full" | "down_payment"

    # ── Fields added to fix existing bugs ──────────────────────────
    # BUG FIX 1: customer_email was already sent by the frontend but
    #            was silently ignored — the Order was never linked to a user.
    customer_email:     Optional[str]  = None

    # BUG FIX 2: frontend sends actual payment percentage (20/30/50/100)
    #            but backend always defaulted to 50 % for any down_payment.
    payment_percentage: Optional[int]  = 100   # e.g. 100 / 50 / 30 / 20

    # Needed for correct invoice totals (tax + shipping are applied here,
    # not just on the frontend).
    shipping_method:    Optional[str]  = "standard"  # standard | express | sameday
    customer_name:      Optional[str]  = "Valued Customer"


class ProductCreate(BaseModel):
    name: str
    basePrice: float
    category: str
    imageUrl: str
    description: str
    stock: int
    sizes: str
    colors: str


class LoginPayload(BaseModel):
    username: str
    password: str


# ── Shipping cost lookup ────────────────────────────────────────────────────────
SHIPPING_COSTS = {"standard": 0.0, "express": 30.0, "sameday": 90.0}
TAX_RATE = 0.065


# ── Background task ────────────────────────────────────────────────────────────
def _send_invoice_email(
    order_id:       int,
    customer_name:  str,
    customer_email: str,
    items:          List[CartItem],
    subtotal:       float,
    tax_amount:     float,
    shipping_cost:  float,
    total_due:      float,
    amount_paid:    float,
    balance_due:    float,
    payment_status: str,
):
    """
    Generates the invoice PDF and sends the confirmation email.
    Runs as a FastAPI BackgroundTask so it never blocks the HTTP response.
    Any exception is caught and logged — it does NOT crash the server.
    """
    try:
        invoice_data = InvoiceData(
            order_id=order_id,
            customer_name=customer_name,
            customer_email=customer_email,
            items=[
                InvoiceItem(name=i.name, quantity=i.quantity, price=i.basePrice)
                for i in items
            ],
            subtotal=subtotal,
            tax_amount=tax_amount,
            shipping_cost=shipping_cost,
            total_due=total_due,
            amount_paid=amount_paid,
            balance_due=balance_due,
            payment_status=payment_status,
        )

        pdf_path = generate_invoice_pdf(invoice_data)

        send_order_confirmation(
            to_email=customer_email,
            customer_name=customer_name,
            order_id=order_id,
            amount_paid=amount_paid,
            balance_due=balance_due,
            is_fully_paid=(balance_due == 0),
            pdf_path=pdf_path,
        )

        # Clean up the temp PDF after sending
        if os.path.exists(pdf_path):
            os.remove(pdf_path)

        print(f"[EMAIL] Invoice sent to {customer_email} for order #{order_id}")

    except Exception as exc:
        # Log the error but do not let it surface to the customer
        print(f"[EMAIL ERROR] Failed to send invoice for order #{order_id}: {exc}")


# ── Product endpoints (unchanged) ──────────────────────────────────────────────

@app.get("/api/products")
def get_all_products(db: Session = Depends(get_db)):
    products = db.query(database.Product).all()
    return [
        {
            "id": p.id, "name": p.name, "basePrice": p.base_price,
            "category": p.category, "imageUrl": p.image_url,
            "description": p.description, "stock": p.stock,
            "sizes": p.sizes, "colors": p.colors,
        }
        for p in products
    ]


@app.post("/api/products")
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    new_product = database.Product(
        name=product.name, base_price=product.basePrice,
        category=product.category, image_url=product.imageUrl,
        description=product.description, stock=product.stock,
        sizes=product.sizes, colors=product.colors,
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return {
        "id": new_product.id, "name": new_product.name,
        "basePrice": new_product.base_price, "category": new_product.category,
        "imageUrl": new_product.image_url, "description": new_product.description,
        "stock": new_product.stock, "sizes": new_product.sizes,
        "colors": new_product.colors,
    }


@app.put("/api/products/{product_id}")
def update_product(product_id: int, product: ProductCreate, db: Session = Depends(get_db)):
    db_product = db.query(database.Product).filter(database.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    db_product.name        = product.name
    db_product.base_price  = product.basePrice
    db_product.category    = product.category
    db_product.image_url   = product.imageUrl
    db_product.description = product.description
    db_product.stock       = product.stock
    db_product.sizes       = product.sizes
    db_product.colors      = product.colors
    db.commit()
    db.refresh(db_product)
    return {
        "id": db_product.id, "name": db_product.name,
        "basePrice": db_product.base_price, "category": db_product.category,
        "imageUrl": db_product.image_url, "description": db_product.description,
        "stock": db_product.stock, "sizes": db_product.sizes,
        "colors": db_product.colors,
    }


# ── Checkout endpoint ──────────────────────────────────────────────────────────

@app.post("/api/checkout")
async def process_checkout(
    payload:          CheckoutPayload,
    background_tasks: BackgroundTasks,
    db:               Session = Depends(get_db),
):
    # ── 1. Validate MOQ ────────────────────────────────────────────
    total_quantity = sum(item.quantity for item in payload.items)
    if total_quantity < 20:
        raise HTTPException(status_code=400, detail="Minimum order of 20 items required.")

    # ── 2. Subtotal with bulk discount ─────────────────────────────
    discount = 0.8 if total_quantity >= 100 else 0.9 if total_quantity >= 50 else 1.0
    subtotal = sum(item.basePrice * item.quantity * discount for item in payload.items)

    # ── 3. Tax + shipping (now calculated server-side too) ─────────
    tax_amount    = round(subtotal * TAX_RATE, 2)
    shipping_cost = SHIPPING_COSTS.get(payload.shipping_method or "standard", 0.0)
    total_due     = round(subtotal + tax_amount + shipping_cost, 2)

    # ── 4. Payment split using the actual percentage the user chose ─
    # BUG FIX: was always 50 % regardless of what the customer selected
    pct          = (payload.payment_percentage or 100) / 100
    amount_paid  = round(total_due * pct, 2)
    balance_due  = round(total_due - amount_paid, 2)
    status       = "Paid in Full" if balance_due == 0 else "Partial Payment"

    # ── 5. Persist order ───────────────────────────────────────────
    new_order = database.Order(
        customer_email=payload.customer_email,   # requires column added in database.py (see note)
        total_items=total_quantity,
        final_total=total_due,
        amount_paid=amount_paid,
        balance_due=balance_due,
        payment_status=status,
    )
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    for item in payload.items:
        db.add(database.OrderItem(
            order_id=new_order.id,
            product_name=item.name,
            quantity=item.quantity,
            price_at_purchase=item.basePrice,
        ))
    db.commit()

    # ── 6. Fire email + invoice in the background ──────────────────
    if payload.customer_email:
        background_tasks.add_task(
            _send_invoice_email,
            order_id=new_order.id,
            customer_name=payload.customer_name or "Valued Customer",
            customer_email=payload.customer_email,
            items=payload.items,
            subtotal=subtotal,
            tax_amount=tax_amount,
            shipping_cost=shipping_cost,
            total_due=total_due,
            amount_paid=amount_paid,
            balance_due=balance_due,
            payment_status=status,
        )

    return {
        "status": "success",
        "order_summary": {
            "id":             new_order.id,         # NOTE: key changed from order_id → id
            "total_items":    new_order.total_items,
            "final_total":    round(new_order.final_total, 2),
            "amount_paid":    round(new_order.amount_paid, 2),
            "balance_due":    round(new_order.balance_due, 2),
            "payment_status": new_order.payment_status,
        },
    }


# ── Orders endpoint (BUG FIX: now returns customer_email) ─────────────────────

@app.get("/api/orders")
def get_all_orders(db: Session = Depends(get_db)):
    orders = db.query(database.Order).order_by(database.Order.id.desc()).all()
    result = []
    for order in orders:
        items = [
            {"name": i.product_name, "quantity": i.quantity, "price": i.price_at_purchase}
            for i in order.items
        ]
        result.append({
            "id":             order.id,
            "customer_email": order.customer_email,   # BUG FIX: was missing — broke "My Orders" filter in App.jsx
            "total_items":    order.total_items,
            "final_total":    order.final_total,
            "amount_paid":    order.amount_paid,
            "balance_due":    order.balance_due,
            "payment_status": order.payment_status,
            "items":          items,
        })
    return result


# ── Auth endpoints (unchanged) ─────────────────────────────────────────────────

@app.post("/api/login")
def login_user(payload: LoginPayload):
    if payload.username == "admin" and payload.password == "admin123":
        return {"status": "success", "role": "admin"}
    elif payload.username == "customer" and payload.password == "customer123":
        return {"status": "success", "role": "customer"}
    raise HTTPException(status_code=401, detail="Invalid username or password")