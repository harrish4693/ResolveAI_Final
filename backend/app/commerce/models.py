from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float
from app.database import Base
from app.shared.models import TimestampMixin

class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tenant_id = Column(String(50), nullable=False, default="default", index=True)
    
    order_number = Column(String(100), unique=True, nullable=False, index=True)
    status = Column(String(50), nullable=False)
    expected_delivery = Column(DateTime(timezone=True), nullable=True)
    tracking_number = Column(String(100), nullable=True)

class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tenant_id = Column(String(50), nullable=False, default="default", index=True)
    
    transaction_id = Column(String(100), unique=True, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False, default="USD")
    status = Column(String(50), nullable=False)
