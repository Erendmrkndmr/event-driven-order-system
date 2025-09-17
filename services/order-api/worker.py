import os, json, pika

RABBITMQ_URL = os.getenv("RABBITMQ_URL")

def main():
    params = pika.URLParameters(RABBITMQ_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.exchange_declare(exchange="acme.events", exchange_type="direct", durable=True)

    # dev : connect to order.placed
    qname = "q.dev.tap"
    ch.queue_declare(queue=qname, durable=True)
    ch.queue_bind(queue=qname, exchange="acme.events", routing_key="order.placed")

    print("[dev-consumer] listening on order.placed ...")
    def cb(ch_, method, props, body):
        try:
            evt = json.loads(body.decode())
        except Exception:
            evt = {"raw": body.decode(errors="ignore")}
        print(f"[dev-consumer] got: rk={method.routing_key} payload={evt}")
        ch_.basic_ack(delivery_tag=method.delivery_tag)

    ch.basic_qos(prefetch_count=20)
    ch.basic_consume(queue=qname, on_message_callback=cb)
    ch.start_consuming()

if __name__ == "__main__":
    main()
