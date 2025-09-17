from sqlalchemy.orm import Session
from . import models
from uuid import uuid4
from decimal import Decimal

def create_order_with_outbox(db: Session, order_data):
    """
    Tek transaction içinde:
    - orders / order_items ekle
    - event_outbox'a order.placed kaydet
    """
    total_amount = Decimal("0.00")
    for item in order_data.items:
        product = db.query(models.Product).filter(models.Product.sku == item.sku).first()
        if not product:
            raise ValueError(f"Product {item.sku} not found")
        total_amount += product.price * item.qty

    order_id = uuid4()
    order = models.Order(
        id=order_id,
        customer_id=order_data.customer_id,
        email=order_data.email,
        status="placed",
        total_amount=total_amount,
    )
    db.add(order)

    for item in order_data.items:
        product = db.query(models.Product).filter(models.Product.sku == item.sku).first()
        db.add(models.OrderItem(
            order_id=order_id,
            sku=item.sku,
            qty=item.qty,
            unit_price=product.price,
        ))

    # outbox event
    payload = {
        "order_id": str(order_id),
        "customer_id": order_data.customer_id,
        "email": order_data.email,
        "items": [item.dict() for item in order_data.items],
        "total_amount": float(total_amount),
    }
    outbox = models.EventOutbox(
        event_type="order.placed",
        payload=payload,
    )
    db.add(outbox)

    db.commit()
    db.refresh(order)
    return order
