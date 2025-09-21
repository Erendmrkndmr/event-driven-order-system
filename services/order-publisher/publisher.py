import os, json, time
import pika
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError

RABBITMQ_URL = os.getenv("RABBITMQ_URL")  # amqp://eda_user:eda_pass@rabbitmq:5672/%2Facme
DATABASE_URL = os.getenv("DATABASE_URL")  # postgresql+psycopg2://acme:acme@postgres:5432/acme
POLL_SEC = float(os.getenv("OUTBOX_POLL_SEC", "1.0"))
BATCH_SIZE = int(os.getenv("OUTBOX_BATCH_SIZE", "100"))

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def connect_rabbitmq_with_retry(max_wait_sec: int = 60):
    attempt = 0
    while True:
        try:
            params = pika.URLParameters(RABBITMQ_URL)
            # bağlantı dayanıklılığı
            params.heartbeat = 30
            params.blocked_connection_timeout = 300
            params.connection_attempts = 5
            params.retry_delay = 2

            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.exchange_declare(exchange="acme.events", exchange_type="direct", durable=True)
            return conn, ch
        except Exception as e:
            attempt += 1
            sleep = min(2 ** attempt, max_wait_sec)
            print(f"[publisher] RabbitMQ connect failed ({e}); retrying in {sleep}s", flush=True)
            time.sleep(sleep)


def get_db_session_with_retry(max_wait_sec: int = 60):
    attempt = 0
    while True:
        try:
            db = SessionLocal()
            db.execute(text("select 1"))
            return db
        except OperationalError as e:
            attempt += 1
            sleep = min(2 ** attempt, max_wait_sec)
            print(f"[publisher] DB connect failed ({e}); retrying in {sleep}s", flush=True)
            time.sleep(sleep)

def publish_batch(channel, rows, db):
    global conn  # reconnect için erişelim (conn'u loop() içinde tanımlıyoruz)
    for r in rows:
        body = json.dumps(r.payload).encode("utf-8")
        published = False
        for attempt in range(2):  # ilk deneme + 1 retry
            try:
                channel.basic_publish(
                    exchange="acme.events",
                    routing_key=r.event_type,
                    body=body,
                    properties=pika.BasicProperties(
                        content_type="application/json",
                        delivery_mode=2,  # persistent
                    ),
                )
                db.execute(text("""
                    UPDATE event_outbox
                       SET status='PUBLISHED', published_at=NOW()
                     WHERE id=:id
                """), {"id": r.id})
                published = True
                break
            except Exception as e:
                print(f"[publisher] publish failed id={r.id} (attempt {attempt+1}): {e}", flush=True)
                # Kanal/bağlantı kapanmış olabilir: yeniden bağlan
                try:
                    channel.close()
                except:  # noqa
                    pass
                try:
                    conn.close()
                except:  # noqa
                    pass
                conn, channel = connect_rabbitmq_with_retry()
        if not published:
            # agresif FAILED yapmıyoruz; kayıt NEW kalsın, loop tekrar deneyecek
            print(f"[publisher] giving up for now id={r.id}; will retry on next loop", flush=True)


def loop():
    global conn
    conn, channel = connect_rabbitmq_with_retry()
    print("[publisher] connected to RabbitMQ", flush=True)

    db = get_db_session_with_retry()
    db.close()
    print("[publisher] connected to DB", flush=True)

    while True:
        try:
            with SessionLocal() as db:
                rows = db.execute(text("""
                    SELECT id, event_type, payload
                      FROM event_outbox
                     WHERE status='NEW'
                  ORDER BY id
                     FOR UPDATE SKIP LOCKED
                     LIMIT :lim
                """), {"lim": BATCH_SIZE}).fetchall()

                if rows:
                    publish_batch(channel, rows, db)
                    db.commit()
        except Exception as e:
            print(f"[publisher] loop error: {e}", flush=True)
            try:
                channel.close()
            except:
                pass
            try:
                conn.close()
            except:
                pass
            conn, channel = connect_rabbitmq_with_retry()
        time.sleep(POLL_SEC)

if __name__ == "__main__":
    loop()
