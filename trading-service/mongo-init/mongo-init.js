db = db.getSiblingDB('admin');

// Create root (ignore if exists)
try {
  db.createUser({
    user: "${MONGO_INITDB_ROOT_USERNAME}",  // Use env vars
    pwd: "${MONGO_INITDB_ROOT_PASSWORD}",
    roles: [{ role: "root", db: "admin" }]
  });
  print("✅ Root user created");
} catch (e) {
  print("ℹ️ Root user already exists");
}

db = db.getSiblingDB('trading_db');
db.createUser({
  user: "trader",
  pwd: "tradingpass123",
  roles: [{ role: "readWrite", db: "trading_db" }]
});
print("✅ Trader user created");

// Create indexes (ignore if exist)
db.orders.createIndex({ "symbol": 1 }, { background: true });
db.orders.createIndex({ "action": 1 }, { background: true });
db.orders.createIndex({ "created_at": -1 }, { background: true });
print("✅ Indexes created");

print("✅ Trading database setup complete!");