import asyncpg
from typing import Dict, List, Optional, Any
import json
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI


app = FastAPI()

class TradingDBClient:
    def __init__(self, dsn: str = None):
        self.pool = None
        self.dsn = dsn or os.getenv(
            "POSTGRES_DSN", 
            "postgresql://trader:securepassword123@postgres-decisions:5432/trading_decisions" 
        )
    
    async def initialize(self):
        print("Initializing TradingDBClient...")
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=5,
            max_size=20,
        )
        print("TradingDBClient initialized.")
    
    @asynccontextmanager
    async def get_connection(self):
        if not self.pool:
            raise RuntimeError("Pool not initialized!")
        async with self.pool.acquire() as conn:
            yield conn

    async def store_decision(self, order_id: str, data: Dict[str, Any]) -> bool:
        async with self.get_connection() as conn:
            try:
                await conn.execute("""
                    INSERT INTO decisions (order_id, symbol, action, confidence, 
                                         risk_score, reasonings, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (order_id) DO UPDATE SET 
                        reasonings = EXCLUDED.reasonings,
                        updated_at = NOW()
                """, order_id, 
                 data.get('symbol'), 
                 data.get('action'),
                 data.get('confidence'),
                 data.get('risk_score'),
                 json.dumps(data),
                 data.get('status', 'open')
                )
                return True
            except Exception as e:
                print(f"DB Error: {e}")
                return False

    async def get_decision(self, order_id: str) -> Optional[Dict[str, Any]]:
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM decisions WHERE order_id = $1", order_id
            )
            if row:
                return dict(row)
            return None

    async def get_recent_decisions(
        self, 
        symbol: Optional[str] = None, 
        limit: int = 50,
        status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            query = "SELECT * FROM decisions WHERE 1=1"
            params = []
            param_idx = 1
            
            if symbol:
                query += f" AND symbol = ${param_idx}"
                params.append(symbol)
                param_idx += 1
            
            if status:
                query += f" AND status = ${param_idx}"
                params.append(status)
                param_idx += 1
            
            query += f" ORDER BY created_at DESC LIMIT ${param_idx}"
            params.append(limit)
            
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def update_pnl(self, order_id: str, pnl: float, status: str = "closed"):
        async with self.get_connection() as conn:
            await conn.execute("""
                UPDATE decisions 
                SET pnl = $1, status = $2, updated_at = NOW()
                WHERE order_id = $3
            """, pnl, status, order_id)

    async def get_performance(self, days: int = 30) -> List[Dict[str, Any]]:
        async with self.get_connection() as conn:
            rows = await conn.fetch("""
                SELECT 
                    symbol,
                    COUNT(*) as trades,
                    AVG(confidence) as avg_confidence,
                    AVG(risk_score) as avg_risk_score,
                    SUM(pnl) as total_pnl,
                    AVG(pnl) as avg_pnl,
                    COUNT(*) FILTER (WHERE pnl > 0) as wins,
                    COUNT(*) FILTER (WHERE pnl < 0) as losses
                FROM decisions 
                WHERE created_at > NOW() - INTERVAL '{} days'
                    AND pnl IS NOT NULL
                GROUP BY symbol
                ORDER BY total_pnl DESC
            """.format(days))
            return [dict(row) for row in rows]

async def get_trading_db():
    global trading_db
    if not trading_db:
        raise RuntimeError("DB not ready!")
    return trading_db


_db_client: Optional[TradingDBClient] = None


async def get_trading_db() -> TradingDBClient:
    global _db_client
    if _db_client is None:
        _db_client = TradingDBClient()
        await _db_client.initialize()
    return _db_client