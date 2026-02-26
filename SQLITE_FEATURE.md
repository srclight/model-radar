# SQLite Database Feature

## Overview

Model Radar now includes SQLite persistence for storing model definitions and ping results. The database is automatically synced from the hardcoded provider definitions, ensuring you always have the latest model list.

## Database Location

```
~/.model-radar/models.db
```

## Commands

### Sync Models to Database

Sync all hardcoded provider models to the SQLite database:

```bash
model-radar db sync
```

**Output:**
```
Syncing models to /home/tim/.model-radar/models.db...
Synced 131 models from 17 providers:
  - nvidia: 41 models
  - groq: 10 models
  - openrouter: 10 models
  ...
```

### Show Database Status

View statistics about the database:

```bash
model-radar db status
```

**Output:**
```
Database: /home/tim/.model-radar/models.db
Models: 131 active, 0 inactive
Providers: 17
Ping results: 0

Per-provider breakdown:
  - nvidia: 41/41 models
  - groq: 10/10 models
  ...
```

### Query Models

Query models with filters:

```bash
# Filter by tier
model-radar db query --tier "S+"

# Filter by provider
model-radar db query --provider "nvidia"

# Filter by minimum tier
model-radar db query --min-tier "S"

# Include inactive models
model-radar db query --inactive
```

**Output:**
```
Found 24 models:
  [S+] DeepSeek V3.2            nvidia/deepseek-ai/deepseek-v3.2
  [S+] Kimi K2.5                nvidia/moonshotai/kimi-k2.5
  ...
```

## Python API

### Sync Models

```python
from model_radar.db import sync_models, init_schema

# Initialize schema and sync
init_schema()
stats = sync_models()
print(f"Synced {sum(stats.values())} models")
```

### Query Models

```python
from model_radar.db import get_all_models, filter_models

# Get all models
models = get_all_models()

# Filter by provider
nvidia_models = filter_models(provider="nvidia")

# Filter by tier
s_plus_models = filter_models(tier="S+")

# Filter by minimum tier
high_tier_models = filter_models(min_tier="S")
```

### Record Ping Results

```python
from model_radar.db import record_ping, get_recent_ping

# Record a ping result
record_ping(
    model_id="llama-3.3-70b-instruct",
    provider_key="groq",
    status="up",
    latency_ms=42.5,
)

# Get recent ping (within TTL)
recent = get_recent_ping(
    model_id="llama-3.3-70b-instruct",
    provider_key="groq",
    ttl_seconds=300,  # 5 minutes
)

if recent:
    print(f"Latency: {recent['latency_ms']}ms")
else:
    print("No recent ping, need to scan")
```

### Get Statistics

```python
from model_radar.db import get_stats, get_provider_stats

# Overall stats
stats = get_stats()
print(f"Models: {stats['active_models']}")
print(f"Ping results: {stats['ping_results']}")

# Per-provider stats
provider_stats = get_provider_stats()
for provider, pstats in provider_stats.items():
    print(f"{provider}: {pstats['active_models']} models")
```

## Database Schema

### Models Table

```sql
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
```

### Ping Results Table

```sql
CREATE TABLE ping_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT NOT NULL,
    provider_key TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms REAL,
    error_detail TEXT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Cache Metadata Table

```sql
CREATE TABLE cache_meta (
    key TEXT PRIMARY KEY,
    value TEXT,
    expires_at TIMESTAMP
);
```

## Future Enhancements (Not Implemented)

The following features are possible extensions but not yet implemented:

1. **Automatic sync on startup** - Auto-sync when server starts
2. **TTL-based ping caching** - Cache ping results with configurable TTL
3. **Historical ping data** - Query latency trends over time
4. **Provider API integration** - Fetch live model lists from providers
5. **Inactive model detection** - Mark models as inactive if they consistently fail

## Testing

All tests pass (111 tests total):

```bash
python -m pytest tests/test_db.py -v
python -m pytest tests/ -v
```

## Notes

- **Backward compatibility**: All existing functionality continues to work
- **No breaking changes**: MCP tool signatures remain the same
- **Privacy**: Database stored locally in `~/.model-radar/`, never sent off-host
- **Sync is idempotent**: Running sync multiple times won't duplicate data
- **Hardcoded-first**: Provider definitions in `providers.py` remain the source of truth
