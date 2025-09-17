-- === Core domain: products / orders / items / payments / email ===
CREATE TABLE IF NOT EXISTS products (
  sku TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  price NUMERIC(12,2) NOT NULL,
  stock_qty INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
  id UUID PRIMARY KEY,
  customer_id TEXT NOT NULL,
  email TEXT NOT NULL,
  status TEXT NOT NULL,               -- placed | reserved | out_of_stock | paid | failed
  total_amount NUMERIC(12,2) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
  id BIGSERIAL PRIMARY KEY,
  order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  sku TEXT NOT NULL REFERENCES products(sku),
  qty INT NOT NULL,
  unit_price NUMERIC(12,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
  id BIGSERIAL PRIMARY KEY,
  order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  status TEXT NOT NULL,               -- completed | failed
  amount NUMERIC(12,2) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_log (
  id BIGSERIAL PRIMARY KEY,
  order_id UUID,
  to_email TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL,               -- sent | failed
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- === EDA patterns: Transactional Outbox + Idempotency ===
CREATE TABLE IF NOT EXISTS event_outbox (
  id BIGSERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  event_id UUID NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  version INT NOT NULL DEFAULT 1,
  payload JSONB NOT NULL,
  published_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'NEW'   -- NEW | PUBLISHED | FAILED
);
CREATE INDEX IF NOT EXISTS idx_event_outbox_status ON event_outbox(status);

CREATE TABLE IF NOT EXISTS processed_events (
  service_name TEXT NOT NULL,
  event_id UUID NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (service_name, event_id)
);

-- === Seed inventory (T-shirt SKUs) ===
INSERT INTO products (sku, name, price, stock_qty) VALUES
  ('TSHIRT-BLK-M','Black T-Shirt M',199.90,20),
  ('TSHIRT-WHT-L','White T-Shirt L',199.90,15),
  ('TSHIRT-GRY-S','Grey T-Shirt S',179.90,10)
ON CONFLICT (sku) DO NOTHING;
