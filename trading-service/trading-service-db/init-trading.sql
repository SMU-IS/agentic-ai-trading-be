-- Trading decisions table (runs automatically on first start)
-- Create table (IF NOT EXISTS handles duplicates)
CREATE TABLE IF NOT EXISTS decisions (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(36) UNIQUE NOT NULL,
    symbol VARCHAR(10) NOT NULL,
    action VARCHAR(10),
    confidence DECIMAL(3,2),
    risk_score DECIMAL(3,2),
    reasonings JSONB NOT NULL,
    pnl DECIMAL(12,4),
    status VARCHAR(20) DEFAULT 'open',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes (IF NOT EXISTS handles duplicates)
CREATE INDEX IF NOT EXISTS idx_symbol_created ON decisions(symbol, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_status_symbol ON decisions(status, symbol);
CREATE INDEX IF NOT EXISTS idx_risk_score ON decisions(risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_order_id ON decisions(order_id);

-- Function for updated_at (CREATE OR REPLACE handles updates)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger (DROP + CREATE handles updates)
DROP TRIGGER IF EXISTS update_decisions_updated_at ON decisions;
CREATE TRIGGER update_decisions_updated_at 
    BEFORE UPDATE ON decisions 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();