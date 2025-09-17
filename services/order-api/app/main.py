from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from . import database, schemas, crud

app = FastAPI(title="Order API")

@app.post("/orders")
def create_order(order: schemas.OrderCreate, db: Session = Depends(database.get_db)):
    try:
        new_order = crud.create_order_with_outbox(db, order)
        return {"order_id": str(new_order.id), "status": new_order.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
