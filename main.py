import os
import threading 
import json
import urllib.request
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session
from supabase import create_client

# Use your SERVICE_ROLE_KEY from Supabase (keep this safe!)
supabaseUrl = os.environ.get("VITE_SUPABASE_URL")
supabase_admin = create_client(supabaseUrl, os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))

import database

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://b2b-apparel-frontend.vercel.app",
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

database.Base.metadata.create_all(bind=database.engine)

# --- SECURITY DEPENDENCY ---
def get_current_user(token: str = Header(...), db: Session = Depends(database.SessionLocal)):
    try:
        user_response = supabase_admin.auth.get_user(token)
        user_id = user_response.user.id
        profile = db.query(database.User).filter(database.User.id == user_id).first()
        if not profile or profile.role != 'admin':
            raise HTTPException(status_code=403, detail="Admin access required")
        return profile
    except Exception as e:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

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


# â”€â”€ Pydantic models â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class CartItem(BaseModel):
    id: str
    name: str
    basePrice: float
    quantity: int


class CheckoutPayload(BaseModel):
    items:              List[CartItem]
    payment_method:     str            # "full" | "down_payment"

    customer_email:     Optional[str]  = None
    payment_percentage: Optional[int]  = 100   
    shipping_method:    Optional[str]  = "standard"  
    customer_name:      Optional[str]  = "Valued Customer"
    
    # â”€â”€ Add these two new lines â”€â”€
    customer_phone:     Optional[str]  = None
    shipping_address:   Optional[str]  = None


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


# â”€â”€ Shipping cost lookup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
SHIPPING_COSTS = {"standard": 0.0, "express": 30.0, "sameday": 90.0}
TAX_RATE = 0.065


# â”€â”€ Background task for Make.com â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _trigger_make_webhook(payload_dict: dict):
    """
    Sends the checkout data to Make.com so it can generate the Google Doc
    invoice and email the customer.
    """
    url = "https://hook.eu1.make.com/rkzx9r8youzm9t7gwwxkhxtr7i5iocma"
    req = urllib.request.Request(url, method="POST")
    req.add_header('Content-Type', 'application/json')
    data = json.dumps(payload_dict).encode('utf-8')
    
    try:
        urllib.request.urlopen(req, data=data)
        print(f"[WEBHOOK] Successfully triggered Make.com for Order #{payload_dict.get('orderId')}")
    except Exception as exc:
        print(f"[WEBHOOK ERROR] Failed to trigger Make.com: {exc}")


# â”€â”€ Product endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ Checkout endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.post("/api/checkout")
async def process_checkout(
    payload: CheckoutPayload,
    db:      Session = Depends(get_db),
):
    # --- 1. Validate MOQ ---
    total_quantity = sum(item.quantity for item in payload.items)
    if total_quantity < 20:
        raise HTTPException(status_code=400, detail="Minimum order of 20 items required.")

    # --- 2. Validate Stock for all items BEFORE committing anything ---
    for item in payload.items:
        # Extract the base numeric ID.
        base_product_id = item.id.split('-')[0]
        db_product = db.query(database.Product).filter(database.Product.id == int(base_product_id)).first()
        if not db_product:
            raise HTTPException(status_code=404, detail=f"Product with ID {base_product_id} not found.")
        if db_product.stock < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {db_product.name}")

    # --- 3. Subtotal with bulk discount ---
    discount = 0.8 if total_quantity >= 100 else 0.9 if total_quantity >= 50 else 1.0
    subtotal = sum(item.basePrice * item.quantity * discount for item in payload.items)

    # --- 4. Tax + shipping ---
    tax_amount    = round(subtotal * TAX_RATE, 2)
    shipping_cost = SHIPPING_COSTS.get(payload.shipping_method or "standard", 0.0)
    total_due     = round(subtotal + tax_amount + shipping_cost, 2)

    # --- 5. Payment split ---
    pct          = (payload.payment_percentage or 100) / 100
    amount_paid  = round(total_due * pct, 2)
    balance_due  = round(total_due - amount_paid, 2)
    status       = "Paid in Full" if balance_due == 0 else "Partial Payment"

    # --- 6. Persist Order and Decrement Stock ---
    new_order = database.Order(
        customer_email=payload.customer_email,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        shipping_address=payload.shipping_address,
        total_items=total_quantity,
        final_total=total_due,
        amount_paid=amount_paid,
        balance_due=balance_due,
        payment_status=status,
    )
    db.add(new_order)
    db.commit() # Commit to generate new_order.id
    db.refresh(new_order)

    for item in payload.items:
        # Decrement Stock
        base_product_id = item.id.split('-')[0]
        db_product = db.query(database.Product).filter(database.Product.id == int(base_product_id)).first()
        db_product.stock -= item.quantity
        
        # Add Order Item
        db.add(database.OrderItem(
            order_id=new_order.id,
            product_name=item.name,
            quantity=item.quantity,
            price_at_purchase=item.basePrice,
        ))
    
    db.commit() # Save stock updates and order items

    # --- 7. Fire Make.com Webhook ---
    if payload.customer_email:
        webhook_payload = {
            "orderId": new_order.id,
            "customerName": payload.customer_name or "Valued Customer",
            "email": payload.customer_email,
            "shipping_method": payload.shipping_method or "standard",
            "subtotal": subtotal,
            "tax_amount": tax_amount,
            "shipping_cost": shipping_cost,
            "totalDue": total_due,
            "amountPaid": amount_paid,
            "balance": balance_due,
            "payment_status": status,
            "items": [
                {"name": i.name, "quantity": i.quantity, "price": i.basePrice} 
                for i in payload.items
            ]
        }
        
        thread = threading.Thread(target=_trigger_make_webhook, args=(webhook_payload,))
        thread.start()

    return {
        "status": "success",
        "order_summary": {
            "id": new_order.id,         
            "total_items": new_order.total_items,
            "final_total": round(new_order.final_total, 2),
            "amount_paid": round(new_order.amount_paid, 2),
            "balance_due": round(new_order.balance_due, 2),
            "payment_status": new_order.payment_status,
        },
    }

@app.post("/api/products/{product_id}/decrement")
def decrement_stock(product_id: int, payload: dict, db: Session = Depends(get_db)):
    # 1. Find the product
    db_product = db.query(database.Product).filter(database.Product.id == product_id).first()
    if not db_product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # 2. Check stock
    quantity_to_subtract = payload.get("quantity", 0)
    if db_product.stock < quantity_to_subtract:
        raise HTTPException(status_code=400, detail=f"Not enough stock for {db_product.name}")
    
    # 3. Update stock
    db_product.stock -= quantity_to_subtract
    db.commit()
    db.refresh(db_product)
    
    return {"status": "success", "new_stock": db_product.stock}

# â”€â”€ Orders endpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
            "customer_email": order.customer_email,
            
            # â”€â”€ Add these three lines so React receives them! â”€â”€
            "customer_name":    order.customer_name,
            "customer_phone":   order.customer_phone,
            "shipping_address": order.shipping_address,
            
            "total_items":    order.total_items,
            "final_total":    order.final_total,
            "amount_paid":    order.amount_paid,
            "balance_due":    order.balance_due,
            "payment_status": order.payment_status,
            "items":          items,
        })
    return result


# â”€â”€ Auth endpoints â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@app.post("/api/login")
def login_user(payload: LoginPayload):
    if payload.username == "admin" and payload.password == "admin123":
        return {"status": "success", "role": "admin"}
    elif payload.username == "customer" and payload.password == "customer123":
        return {"status": "success", "role": "customer"}
    raise HTTPException(status_code=401, detail="Invalid username or password")

@app.get("/api/users")
def get_all_users(db: Session = Depends(get_db), current_user: database.User = Depends(get_current_user)):
    users = db.query(database.User).all()
    return [{"id": u.id, "email": u.email, "role": u.role, "created_at": u.created_at} for u in users]

@app.delete("/api/users/{user_id}")
def delete_user(user_id: str, current_user: database.User = Depends(get_current_user)):
    supabase_admin.auth.admin.delete_user(user_id)
    return {"status": "success"}