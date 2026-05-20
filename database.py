from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from datetime import datetime



SQLALCHEMY_DATABASE_URL = "postgresql://postgres.urgcwtbzfzwgcsskjoip:B2B_ECommerc3_Web@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    total_items = Column(Integer)
    final_total = Column(Float)
    amount_paid = Column(Float)
    balance_due = Column(Float)
    payment_status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    customer_email = Column(String, nullable=True)
    
    # --- NEW: Relationship linking to the items ---
    items = relationship("OrderItem", back_populates="order")
    # Inside your Order model class:
    customer_phone = Column(String, nullable=True)
    shipping_address = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)

# --- NEW: The Line-Item Table ---
class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id")) # Links to Order table
    product_name = Column(String) 
    quantity = Column(Integer)
    price_at_purchase = Column(Float)
    
    order = relationship("Order", back_populates="items")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    base_price = Column(Float)
    category = Column(String)
    image_url = Column(String)
    description = Column(String)
    stock = Column(Integer)
    sizes = Column(String)
    colors = Column(String)