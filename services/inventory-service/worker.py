import os, json, uuid
import pika
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

RABBIT_URL = os.getenv("RABBITMQ_URL")  # amqp://eda_user:eda_pass@rabbitmq:5672/%2Facme
DB_URL = os.getenv("DATABASE_URL")      # postgresql+psycopg2://acme:acme@postgres:5432/acme
SERVICE_NAME = "inventory-service"

engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except:
        db.rollback()
        raise
    finally:
        db.close()

def ensure_exchange(ch):
    ch.exchange_declare(exchange="acme.events", exchange_type="direct", durable=True)

def publish(ch, event_type: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    ch.basic_publish(
        exchange="acme.events",
        routing_key=event_type,
        body=body,
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2),
    )

def already_processed(db, key: str) -> bool:
    row = db.execute(
        text("SELECT 1 FROM processed_events WHERE service_name=:s AND event_id::text=:e"),
        {"s": SERVICE_NAME, "e": key},
    ).fetchone()
    return row is not None

def mark_processed(db, key: str):
    db.execute(
        text("INSERT INTO processed_events(service_name, event_id) VALUES(:s, :e) ON CONFLICT DO NOTHING"),
        {"s": SERVICE_NAME, "e": key},
    )

def handle_order_placed(ch, db, evt: dict):
    order_id = evt["order_id"]
    print(f"[inventory] processing order_id={order_id}", flush=True)  # <-- EK

    if already_processed(db, order_id):
        print(f"[inventory] skip already processed order_id={order_id}", flush=True)  # <-- EK
        return

    try:
        for item in evt["items"]:
            db.execute(text("SELECT 1 FROM products WHERE sku=:sku FOR UPDATE"), {"sku": item["sku"]})
            row = db.execute(text("SELECT stock_qty FROM products WHERE sku=:sku"), {"sku": item["sku"]}).fetchone()
            qty = int(item["qty"])
            if row is None or row[0] < qty:
                print(f"[inventory] OUT OF STOCK sku={item['sku']} need={qty} have={0 if row is None else row[0]}", flush=True)  # <-- EK
                db.execute(text("UPDATE orders SET status='out_of_stock' WHERE id::text=:oid"), {"oid": order_id})
                mark_processed(db, order_id)
                publish(ch, "order.out_of_stock", {"order_id": order_id, "reason": "insufficient_stock"})
                return

        for item in evt["items"]:
            db.execute(text("UPDATE products SET stock_qty=stock_qty - :q WHERE sku=:sku"),
                       {"q": int(item["qty"]), "sku": item["sku"]})

        db.execute(text("UPDATE orders SET status='reserved' WHERE id::text=:oid"), {"oid": order_id})
        mark_processed(db, order_id)
        print(f"[inventory] RESERVED order_id={order_id}", flush=True)  # <-- EK
        publish(ch, "inventory.reserved", {"order_id": order_id})
    except Exception as e:
        print(f"[inventory] error: {e}", flush=True)
        raise

def main():
    # RabbitMQ bağlantısı (retry)
    while True:
        try:
            params = pika.URLParameters(RABBIT_URL)
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ensure_exchange(ch)
            break
        except Exception as e:
            print(f"[inventory] rabbit connect failed: {e}; retrying...", flush=True)

    # Kuyruk ve binding
    qname = "q.inventory.order-placed"
    ch.queue_declare(queue=qname, durable=True)
    ch.queue_bind(queue=qname, exchange="acme.events", routing_key="order.placed")

    print("[inventory] listening on order.placed ...", flush=True)

    def cb(ch_, method, props, body):
        try:
            evt = json.loads(body.decode())
            with session_scope() as db:
                handle_order_placed(ch_, db, evt)
            ch_.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as e:
            print(f"[inventory] cb exception: {e}", flush=True)
            # dev: ack'liyoruz ki requeue döngüsü olmasın
            ch_.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_qos(prefetch_count=10)
    ch.basic_consume(queue=qname, on_message_callback=cb)
    ch.start_consuming()

if __name__ == "__main__":
    # DB warm-up retry
    ready = False
    while not ready:
        try:
            with session_scope() as db:
                db.execute(text("select 1"))
            ready = True
        except OperationalError as e:
            print(f"[inventory] DB connect failed: {e}; retrying...", flush=True)
    main()
