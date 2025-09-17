PROJECT=event-driven-order-system

config:
	docker compose config

reset:
	docker compose down -v || true
	docker system prune -f || true

up:
	docker compose build
	docker compose up -d
	docker compose ps

logs:
	docker logs -f eda-orderpublisher & \
	docker logs -f eda-dev-consumer

psql:
	docker exec -it eda-postgres psql -U acme -d acme

smoke:
	curl -s -X POST http://localhost:8000/orders \
	  -H "Content-Type: application/json" \
	  -d '{"customer_id":"C1","email":"c1@example.com","items":[{"sku":"TSHIRT-BLK-M","qty":1}]}'
