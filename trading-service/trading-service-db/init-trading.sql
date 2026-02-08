-- Orders table only
CREATE TABLE IF NOT EXISTS Orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(36) UNIQUE NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    action VARCHAR(100),
    reasonings TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON Orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_action ON Orders(action);
CREATE INDEX IF NOT EXISTS idx_orders_created ON Orders(created_at DESC);

-- Function for updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for Orders table only
DROP TRIGGER IF EXISTS update_orders_updated_at ON Orders;
CREATE TRIGGER update_orders_updated_at 
    BEFORE UPDATE ON Orders 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
