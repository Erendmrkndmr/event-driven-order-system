import os, json, random, time
import pika
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

RABBIT_URL = os.getenv("RABBITMQ_URL")
DB_URL = os.getenv("DATABASE_URL")
SERVICE_NAME = "payment-service"

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

def handle_inventory_reserved(ch, db, evt: dict):
    order_id = evt["order_id"]
    print(f"[payment] processing order_id={order_id}", flush=True)

    if already_processed(db, order_id):
        print(f"[payment] skip already processed order_id={order_id}", flush=True)
        return

    success = random.random() < float(os.getenv("PAYMENT_SUCCESS_RATE", "0.9"))

    if success:
        db.execute(text("UPDATE orders SET status='paid' WHERE id::text=:oid"), {"oid": order_id})
        mark_processed(db, order_id)
        publish(ch, "payment.completed", {"order_id": order_id})
        print(f"[payment] COMPLETED order_id={order_id}", flush=True)
    else:
        db.execute(text("UPDATE orders SET status='payment_failed' WHERE id::text=:oid"), {"oid": order_id})
        mark_processed(db, order_id)
        publish(ch, "payment.failed", {"order_id": order_id, "reason": "card_declined"})
        print(f"[payment] FAILED order_id={order_id}", flush=True)

def connect_rabbit_with_retry(max_wait=60):
    attempt = 0
    while True:
        try:
            params = pika.URLParameters(RABBIT_URL)
            params.heartbeat = 30
            params.blocked_connection_timeout = 300
            params.connection_attempts = 5
            params.retry_delay = 2
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ensure_exchange(ch)
            return conn, ch
        except Exception as e:
            attempt += 1
            sleep = min(2 ** attempt, max_wait)
            print(f"[payment] rabbit connect failed: {e}; retrying in {sleep}s", flush=True)
            time.sleep(sleep)

def consume_forever():
    while True:
        try:
            conn, ch = connect_rabbit_with_retry()
            qname = "q.payment.inventory-reserved"
            ch.queue_declare(queue=qname, durable=True)
            ch.queue_bind(queue=qname, exchange="acme.events", routing_key="inventory.reserved")

            print("[payment] listening on inventory.reserved ...", flush=True)

            def cb(ch_, method, props, body):
                try:
                    evt = json.loads(body.decode())
                    with session_scope() as db:
                        handle_inventory_reserved(ch_, db, evt)
                    ch_.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    print(f"[payment] cb exception: {e}", flush=True)
                    ch_.basic_ack(delivery_tag=method.delivery_tag)

            ch.basic_qos(prefetch_count=10)
            ch.basic_consume(queue=qname, on_message_callback=cb)
            ch.start_consuming()
        except Exception as e:
            print(f"[payment] consuming error: {e}; reconnecting...", flush=True)
            try:
                ch.close()
            except:
                pass
            try:
                conn.close()
            except:
                pass
            time.sleep(2)

if __name__ == "__main__":
    try:
        with session_scope() as db:
            db.execute(text("select 1"))
        print("[payment] DB ready", flush=True)
    except Exception as e:
        print(f"[payment] DB warm-up error: {e}", flush=True)
    consume_forever()
