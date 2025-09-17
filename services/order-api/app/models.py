from sqlalchemy import Column, String, Numeric, Integer, TIMESTAMP, ForeignKey, JSON, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from .database import Base

class Product(Base):
    __tablename__ = "products"
    sku = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    price = Column(Numeric(12,2), nullable=False)
    stock_qty = Column(Integer, nullable=False, server_default="0")

class Order(Base):
    __tablename__ = "orders"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(String, nullable=False)
    email = Column(String, nullable=False)
    status = Column(String, nullable=False)
    total_amount = Column(Numeric(12,2), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))
    items = relationship("OrderItem", back_populates="order")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    sku = Column(String, ForeignKey("products.sku"), nullable=False)
    qty = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12,2), nullable=False)
    order = relationship("Order", back_populates="items")

class EventOutbox(Base):
    __tablename__ = "event_outbox"
    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, nullable=False)
    event_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    occurred_at = Column(TIMESTAMP(timezone=True), server_default=text("now()"))
    version = Column(Integer, nullable=False, server_default="1")
    payload = Column(JSON, nullable=False)
    published_at = Column(TIMESTAMP(timezone=True), nullable=True)
    status = Column(String, nullable=False, server_default="NEW")
