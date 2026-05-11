from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
import database
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "http://localhost:5173",               # Keeps your local testing working
    "http://127.0.0.1:5173",               
    "https://b2b-apparel-frontend.vercel.app"   # <--- PASTE YOUR ACTUAL VERCEL URL HERE!
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, PUT, etc.)
    allow_headers=["*"],  # Allows all headers
)

database.Base.metadata.create_all(bind=database.engine)

@app.on_event("startup")
def seed_inventory():
    db = database.SessionLocal()
    if db.query(database.Product).count() == 0:
        initial_products = [
            database.Product(name="Heavyweight Blank Hoodie", base_price=25.00, category="Hoodies", image_url="", description="Premium 400gsm cotton heavy hoodie.", stock=500, sizes="S, M, L, XL", colors="Black, Heather Gray"),
            database.Product(name="Premium Cotton Tee", base_price=15.00, category="T-Shirts", image_url="", description="100% combed ring-spun cotton.", stock=1200, sizes="S, M, L, XL, XXL, 3XL", colors="White, Black, Navy"),
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

class CartItem(BaseModel):
    id: str 
    name: str
    basePrice: float
    quantity: int

class CheckoutPayload(BaseModel):
    items: List[CartItem]
    payment_method: str

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

@app.get("/api/products")
def get_all_products(db: Session = Depends(get_db)):
    products = db.query(database.Product).all()
    return [{
        "id": p.id, "name": p.name, "basePrice": p.base_price, 
        "category": p.category, "imageUrl": p.image_url, 
        "description": p.description, "stock": p.stock, 
        "sizes": p.sizes, "colors": p.colors
    } for p in products]

@app.post("/api/products")
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    new_product = database.Product(
        name=product.name, base_price=product.basePrice,
        category=product.category, image_url=product.imageUrl,
        description=product.description, stock=product.stock,
        sizes=product.sizes, colors=product.colors
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    return {"id": new_product.id, "name": new_product.name, "basePrice": new_product.base_price, "category": new_product.category, "imageUrl": new_product.image_url, "description": new_product.description, "stock": new_product.stock, "sizes": new_product.sizes, "colors": new_product.colors}

@app.put("/api/products/{product_id}")
def update_product(product_id: int, product: ProductCreate, db: Session = Depends(get_db)):
    db_product = db.query(database.Product).filter(database.Product.id == product_id).first()
    if not db_product: raise HTTPException(status_code=404, detail="Product not found")
    db_product.name = product.name
    db_product.base_price = product.basePrice
    db_product.category = product.category
    db_product.image_url = product.imageUrl
    db_product.description = product.description
    db_product.stock = product.stock
    db_product.sizes = product.sizes
    db_product.colors = product.colors
    db.commit()
    db.refresh(db_product)
    return {"id": db_product.id, "name": db_product.name, "basePrice": db_product.base_price, "category": db_product.category, "imageUrl": db_product.image_url, "description": db_product.description, "stock": db_product.stock, "sizes": db_product.sizes, "colors": db_product.colors}

@app.post("/api/checkout")
async def process_checkout(payload: CheckoutPayload, db: Session = Depends(get_db)):
    total_quantity = sum(item.quantity for item in payload.items)
    if total_quantity < 20: raise HTTPException(status_code=400, detail="Minimum order of 20 items required.")

    discount_multiplier = 0.8 if total_quantity >= 100 else 0.9 if total_quantity >= 50 else 1.0
    total_price = sum((item.basePrice * item.quantity) * discount_multiplier for item in payload.items)

    amount_paid = total_price * 0.50 if payload.payment_method == "down_payment" else total_price
    balance_due = total_price - amount_paid if payload.payment_method == "down_payment" else 0.0
    status = "Partial Payment" if payload.payment_method == "down_payment" else "Paid in Full"

    # Save Master Order
    new_order = database.Order(total_items=total_quantity, final_total=total_price, amount_paid=amount_paid, balance_due=balance_due, payment_status=status)
    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    # --- NEW: Loop through cart and save exact Line Items ---
    for item in payload.items:
        order_item = database.OrderItem(
            order_id=new_order.id,
            product_name=item.name, # Name already contains Size/Color from React
            quantity=item.quantity,
            price_at_purchase=item.basePrice
        )
        db.add(order_item)
    db.commit()

    return {"status": "success", "order_summary": {"order_id": new_order.id, "total_items": new_order.total_items, "final_total": round(new_order.final_total, 2), "amount_paid": round(new_order.amount_paid, 2), "balance_due": round(new_order.balance_due, 2), "payment_status": new_order.payment_status}}

# --- UPDATED: Fetch orders and package their specific items inside ---
@app.get("/api/orders")
def get_all_orders(db: Session = Depends(get_db)):
    orders = db.query(database.Order).order_by(database.Order.id.desc()).all()
    result = []
    for order in orders:
        # Extract the related items
        items = [{"name": i.product_name, "quantity": i.quantity, "price": i.price_at_purchase} for i in order.items]
        
        result.append({
            "id": order.id,
            "total_items": order.total_items,
            "final_total": order.final_total,
            "amount_paid": order.amount_paid,
            "balance_due": order.balance_due,
            "payment_status": order.payment_status,
            "items": items # Attach line items to the response
        })
    return result

# --- NEW: Admin Login Endpoint ---
# --- UPDATED: Role-Based Login Endpoint ---
@app.post("/api/login")
def login_user(payload: LoginPayload):
    # Admin Account
    if payload.username == "admin" and payload.password == "admin123":
        return {"status": "success", "role": "admin"}
    
    # Customer/Wholesale Buyer Account
    elif payload.username == "customer" and payload.password == "customer123":
        return {"status": "success", "role": "customer"}
    
    raise HTTPException(status_code=401, detail="Invalid username or password")