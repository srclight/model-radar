# SQLite Database Implementation Plan

## Goal
Add SQLite persistence to model-radar to:
1. Store model definitions synced from hardcoded providers
2. Enable future features (ping history, quality tracking, etc.)
3. Keep hardcoded definitions as source of truth
4. Sync on-demand, not continuously

---

## Phase 1: Database Module (`db.py`)

### Schema Design

```sql
-- Models table (synced from hardcoded definitions)
CREATE TABLE models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_key TEXT NOT NULL,
    model_id TEXT NOT NULL,
    label TEXT NOT NULL,
    tier TEXT NOT NULL,
    swe_score TEXT,
    context_window TEXT,
    last_pinged_at TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(provider_key, model_id)
);

-- Ping results (time-series, can be pruned later)
CREATE TABLE ping_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    provider_key TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms REAL,
    error_detail TEXT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cache metadata (for TTL-based caching, future use)
CREATE TABLE cache_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    expires_at TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider_key);
CREATE INDEX IF NOT EXISTS idx_models_active ON models(is_active);
CREATE INDEX IF NOT EXISTS idx_ping_results_model ON ping_results(model_id, provider_key);
CREATE INDEX IF NOT EXISTS idx_ping_results_time ON ping_results(recorded_at DESC);
```

### Database Class Methods

```python
class Database:
    def __init__(self, db_path: str = None)
    def close()
    
    # Schema management
    def init_schema()  # Create tables if not exist
    
    # Model operations
    def sync_models() -> int  # Sync hardcoded models, return count
    def get_all_models() -> list[Model]
    def get_model(provider_key: str, model_id: str) -> Model | None
    def get_models_by_provider(provider_key: str) -> list[Model]
    def get_models_by_tier(tier: str) -> list[Model]
    def get_models_by_min_tier(min_tier: str) -> list[Model]
    def mark_model_inactive(provider_key: str, model_id: str)
    
    # Ping result operations
    def record_ping(model_id: str, provider_key: str, status: str, 
                    latency_ms: float | None, error_detail: str | None)
    def get_recent_ping(model_id: str, provider_key: str, 
                        ttl_seconds: int = 300) -> PingResult | None
    def get_ping_history(model_id: str, provider_key: str, 
                         limit: int = 100) -> list[PingResult]
    
    # Utility
    def get_stats() -> dict  # Count of models, pings, etc.
```

---

## Phase 2: Integration

### Update `providers.py`
- Keep hardcoded definitions (source of truth)
- Add `sync_to_db()` function to sync models on startup
- Modify `get_all_models()` to optionally read from DB
- Keep backward compatibility

### Update `scanner.py`
- Import `Database` class
- After ping, record result to DB
- Optionally check for cached ping before scanning

### Update `config.py`
- Add DB path configuration
- Default: `~/.model-radar/models.db`

---

## Phase 3: CLI Commands

### `model-radar db sync`
```bash
# Sync hardcoded models to SQLite
model-radar db sync

# Output:
# Synced 134 models from 17 providers to ~/.model-radar/models.db
# - nvidia: 49 models
# - groq: 10 models
# - ...
```

### `model-radar db status`
```bash
# Show database statistics
model-radar db status

# Output:
# Database: ~/.model-radar/models.db
# Models: 134 total (134 active)
# Providers: 17
# Ping results: 1,234
# Last sync: 2026-02-26 10:30:00
```

### `model-radar db query` (optional)
```bash
# Query models with filters
model-radar db query --provider nvidia --tier S+
```

---

## Phase 4: Testing

### Test Cases
1. **Schema creation**: Verify tables created correctly
2. **Sync logic**: 
   - First sync inserts all models
   - Second sync updates existing, adds new
   - Handles removed models (mark inactive)
3. **Model queries**: Filter by provider, tier, min_tier
4. **Ping recording**: Store and retrieve ping results
5. **TTL caching**: Expire old cached results
6. **Concurrency**: Multiple processes accessing DB
7. **Migration path**: Fresh install vs existing config

### Test Files
- `tests/test_db.py` - Database operations
- `tests/test_sync.py` - Sync logic
- `tests/test_ping_cache.py` - Ping result caching

---

## Implementation Order

1. ✅ Write `db.py` with schema and basic operations
2. ✅ Add sync logic (`sync_models()`)
3. ✅ Add CLI commands (`db sync`, `db status`)
4. ✅ Write tests for db module
5. ✅ Integrate with `providers.py` (optional DB read)
6. ✅ Integrate with `scanner.py` (record pings)
7. ✅ Test end-to-end

---

## File Structure
```
src/model_radar/
  db.py              # NEW: Database module
  providers.py       # MODIFIED: Add sync_to_db()
  scanner.py         # MODIFIED: Record pings to DB
  cli.py             # MODIFIED: Add db commands
  config.py          # MODIFIED: Add DB path config
  
tests/
  test_db.py         # NEW: Database tests
  test_sync.py       # NEW: Sync tests
```

---

## Configuration

Add to `~/.model-radar/config.json`:
```json
{
  "database_path": "~/.model-radar/models.db",
  "auto_sync_on_startup": true,
  "ping_cache_ttl_seconds": 300
}
```

---

## Notes

- **Backward compatibility**: All existing functionality must continue to work
- **No breaking changes**: MCP tool signatures remain the same
- **Performance**: DB operations should be fast (<10ms for queries)
- **Privacy**: Database stored locally, never sent off-host
- **Cleanup**: Old ping results can be pruned in future (not implemented yet)
