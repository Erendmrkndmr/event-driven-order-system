# Event-Driven Order Processing System

This project is an **Event-Driven Architecture (EDA)** reimplementation of Acme Corp’s e-commerce order processing system. The goal is to make the order workflow modular, scalable, and easily extensible.

## 1. Architecture Overview

- **Order API** – Receives orders, stores them in the database, and writes an `OrderPlaced` event to the outbox table.
- **Outbox Publisher** – Publishes `NEW` events from the outbox table to RabbitMQ.
- **Inventory Service** – Consumes `order.placed` events; checks and reduces stock, then emits `inventory.reserved` or `order.out_of_stock`.
- **Payment Service** – Consumes `inventory.reserved` events; simulates payment, then emits `payment.completed` or `payment.failed`.
- **Notification Service** – Consumes `payment.*` and `order.out_of_stock` events; simulates email notifications via logs.

This design allows new services (Analytics, Loyalty, Fraud Detection, etc.) to be added by subscribing to RabbitMQ without touching existing code.

## 2. Project Structure

```
event-driven-order-system/
├── db/                     # PostgreSQL init scripts (tables + seed data)
│   └── init.sql
├── services/
│   ├── order-api/           # FastAPI-based Order API
│   ├── order-publisher/     # Outbox Publisher
│   ├── inventory-service/   # Stock management service
│   ├── payment-service/     # Payment simulation service
│   └── notification-service/# Notification service
├── docker-compose.yml       # Orchestrates all services
└── README.md
```

**Service Summary:**

| Service            | Description |
|-------------------|-------------|
| **postgres**      | Persistent data; tables and seed data from `db/init.sql` |
| **rabbitmq**      | Event bus; `acme.events` exchange; management UI at `localhost:15672` |
| **orderapi**      | Order API; FastAPI `POST /orders` |
| **orderpublisher**| Outbox publisher; pushes to RabbitMQ |
| **inventory**     | Stock management; listens to `order.placed` |
| **payment**       | Payment simulation; listens to `inventory.reserved` |
| **notification**  | Notification; listens to `payment.*` and `order.out_of_stock` |

## 3. How to Run (Step by Step)

### Prerequisites
- Docker and Docker Compose installed.

### Start the Services
1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd event-driven-order-system
   ```

2. Start all services:
   ```bash
   docker compose up -d
   ```

3. Check status:
   ```bash
   docker compose ps
   ```

### Verify Services
- **Order API Swagger UI**: `http://localhost:8000/docs`
- **RabbitMQ Management UI**: `http://localhost:15672`  
  Username: `eda_user` Password: `eda_pass`

### Follow Logs
```bash
docker logs -f eda-inventory
docker logs -f eda-payment
docker logs -f eda-notification
docker logs -f eda-orderpublisher
```

### Stop Services
```bash
docker compose down         # stops and removes containers
docker compose down -v      # removes volumes too (DB reset)
```

## 4. Testing the System

### Happy Path (Stock Available)
```bash
curl -s -X POST http://localhost:8000/orders  -H "Content-Type: application/json"  -d '{"customer_id":"C100","email":"c100@example.com","items":[{"sku":"TSHIRT-BLK-M","qty":1}]}'
```
Expected:
- Inventory: `RESERVED`
- Payment: `COMPLETED`
- Notification: “Order Paid” log message

### Out of Stock Scenario
```bash
curl -s -X POST http://localhost:8000/orders  -H "Content-Type: application/json"  -d '{"customer_id":"C200","email":"c200@example.com","items":[{"sku":"TSHIRT-GRY-S","qty":999}]}'
```
Expected:
- Inventory: `out_of_stock`
- Notification: “Out of Stock” log message

### Check Database
```bash
docker exec -it eda-postgres psql -U acme -d acme -c "select id,status from orders order by created_at desc limit 5;"

docker exec -it eda-postgres psql -U acme -d acme -c "select sku,stock_qty from products where sku='TSHIRT-BLK-M';"

docker exec -it eda-postgres psql -U acme -d acme -c "select id,event_type,status from event_outbox order by id desc limit 5;"
```

## 5. Database Schema (Summary)

- `orders` – order records (`id`, `customer_id`, `email`, `status`, `created_at`)
- `order_items` – order lines (`order_id`, `sku`, `qty`, `unit_price`)
- `products` – product stock (`sku`, `stock_qty`, `price`)
- `event_outbox` – events to be published (`event_type`, `payload`, `status`)
- `processed_events` – per-service idempotency record

Initial product stock is loaded via `db/init.sql`.

## 6. Test Scenarios

- When an order is placed, stock decreases, payment completes, and notification logs appear.
- When stock is insufficient, the order status becomes `out_of_stock` and notification logs appear.
- By changing `PAYMENT_SUCCESS_RATE`, you can test payment failure scenarios.

## 7. Notes

- Each service has its own Docker image → isolated dependencies, easy scaling.
- To add a new service, simply subscribe to the RabbitMQ exchange.
- This project is being developed on the `dev` branch, to be merged to `main` later.

---

