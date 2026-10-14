CREATE TABLE IF NOT EXISTS import_batch (
 id INTEGER PRIMARY KEY, source_file TEXT NOT NULL, file_hash TEXT NOT NULL, adapter TEXT NOT NULL,
 imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, row_count INTEGER NOT NULL DEFAULT 0,
 wallet_card_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(file_hash, wallet_card_id)
);
CREATE TABLE IF NOT EXISTS "transaction" (
 id INTEGER PRIMARY KEY, wallet_card_id TEXT NOT NULL, import_batch_id INTEGER REFERENCES import_batch(id),
 transaction_date TEXT NOT NULL, posted_date TEXT, amount INTEGER NOT NULL, currency TEXT NOT NULL DEFAULT 'USD',
 raw_description TEXT NOT NULL, normalized_description TEXT NOT NULL, merchant_id TEXT,
 category TEXT NOT NULL DEFAULT 'other', issuer_category TEXT, mcc INTEGER, channel TEXT NOT NULL DEFAULT 'in_person',
 confidence REAL NOT NULL DEFAULT 0, is_refund INTEGER NOT NULL DEFAULT 0, is_fee INTEGER NOT NULL DEFAULT 0,
 is_payment INTEGER NOT NULL DEFAULT 0, is_foreign INTEGER NOT NULL DEFAULT 0,
 dedupe_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS transaction_card_date ON "transaction"(wallet_card_id, transaction_date);
CREATE INDEX IF NOT EXISTS transaction_dedupe ON "transaction"(dedupe_hash);
CREATE TABLE IF NOT EXISTS transaction_override (
 transaction_id INTEGER REFERENCES "transaction"(id), field TEXT NOT NULL, value TEXT NOT NULL,
 set_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(transaction_id, field)
);
CREATE TABLE IF NOT EXISTS merchant_alias (
 normalized_description TEXT PRIMARY KEY, merchant_id TEXT, category TEXT, mcc INTEGER,
 source TEXT NOT NULL, confidence REAL NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS statement (
 wallet_card_id TEXT NOT NULL, close_date TEXT NOT NULL, statement_balance INTEGER NOT NULL,
 source TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(wallet_card_id, close_date)
);
CREATE TABLE IF NOT EXISTS credit_usage (
 id INTEGER PRIMARY KEY, wallet_card_id TEXT NOT NULL, credit_id TEXT NOT NULL,
 period_start TEXT NOT NULL, period_end TEXT NOT NULL, amount_used INTEGER NOT NULL, source TEXT NOT NULL,
 transaction_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(wallet_card_id, credit_id, period_start, transaction_id)
);
CREATE TABLE IF NOT EXISTS recommendation_log (
 id INTEGER PRIMARY KEY, requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, context_json TEXT NOT NULL,
 result_json TEXT NOT NULL, chosen_card_id TEXT, feedback TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS finding (
 id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, severity TEXT NOT NULL,
 dollar_impact REAL, title TEXT NOT NULL, detail TEXT NOT NULL, evidence_json TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, dismissed_at TEXT, generation TEXT
);
CREATE TABLE IF NOT EXISTS assistant_message (
 id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
 tool_calls_json TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
