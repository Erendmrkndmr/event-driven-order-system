from pydantic import BaseModel, EmailStr
from typing import List

class OrderItemCreate(BaseModel):
    sku: str
    qty: int

class OrderCreate(BaseModel):
    customer_id: str
    email: EmailStr
    items: List[OrderItemCreate]
