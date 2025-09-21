import os, json, time
import pika
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

RABBIT_URL = os.getenv("RABBITMQ_URL")
DB_URL = os.getenv("DATABASE_URL")
SERVICE_NAME = "notification-service"

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

def fake_send_email(to: str, subject: str, body: str):
    print(f"[notification] Email TO={to} SUBJECT={subject} BODY={body}", flush=True)

def handle_event(evt_type: str, payload: dict):
    order_id = payload.get("order_id")
    with session_scope() as db:
        if already_processed(db, order_id):
            return

        row = db.execute(text("SELECT email FROM orders WHERE id::text=:oid"),
                         {"oid": order_id}).fetchone()
        email = row[0] if row else "unknown@example.com"

        if evt_type == "payment.completed":
            fake_send_email(email, "Order Paid", f"Order {order_id} paid successfully.")
        elif evt_type == "payment.failed":
            fake_send_email(email, "Payment Failed", f"Order {order_id} payment failed.")
        elif evt_type == "order.out_of_stock":
            fake_send_email(email, "Out of Stock", f"Order {order_id} is out of stock.")
        mark_processed(db, order_id)

def connect_rabbit_with_retry():
    while True:
        try:
            params = pika.URLParameters(RABBIT_URL)
            params.heartbeat = 30
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ensure_exchange(ch)
            return conn, ch
        except Exception as e:
            print(f"[notification] rabbit connect failed: {e}; retrying...", flush=True)
            time.sleep(2)

def consume_forever():
    while True:
        try:
            conn, ch = connect_rabbit_with_retry()
            bindings = [
                ("q.notification.payment-completed",  "payment.completed"),
                ("q.notification.payment-failed",     "payment.failed"),
                ("q.notification.order-out-of-stock", "order.out_of_stock"),
            ]
            for q, rk in bindings:
                ch.queue_declare(queue=q, durable=True)
                ch.queue_bind(queue=q, exchange="acme.events", routing_key=rk)

            print("[notification] listening ...", flush=True)

            def mk_cb(expected_type):
                def _cb(ch_, method, props, body):
                    evt = json.loads(body.decode())
                    handle_event(expected_type, evt)
                    ch_.basic_ack(delivery_tag=method.delivery_tag)
                return _cb

            for q, rk in bindings:
                ch.basic_consume(queue=q, on_message_callback=mk_cb(rk))

            ch.start_consuming()
        except Exception as e:
            print(f"[notification] error: {e}; reconnecting...", flush=True)
            time.sleep(2)

if __name__ == "__main__":
    try:
        with session_scope() as db:
            db.execute(text("select 1"))
        print("[notification] DB ready", flush=True)
    except Exception as e:
        print(f"[notification] DB warm-up error: {e}", flush=True)
    print("[notification] starting consumer...", flush=True)
    consume_forever()
