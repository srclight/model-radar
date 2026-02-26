# Free Models Analysis

## Your Questions Answered

### 1. "How do we know which ones are free?"

**OpenRouter:** Models with `:free` suffix or `-free` in the name are free tier. The API response includes pricing info where `"pricing": {"prompt": 0, "completion": 0}` indicates free models.

**NVIDIA & Groq:** No explicit "free" tier - they use rate-limited free access with your API key.

### 2. "Are there models on our list that are now obsolete?"

**YES! Found 9 potentially obsolete models:**

| Tier | Provider | Model | Status |
|------|----------|-------|--------|
| S+ | OpenRouter | qwen/qwen3-coder:480b-free | ❌ Not in live API |
| S+ | OpenRouter | mistralai/devstral-2-free | ❌ Not in live API |
| A | OpenRouter | mimo-v2-flash-free | ❌ Not in live API |
| S | OpenRouter | deepseek/deepseek-r1-0528:free | ❌ Not in live API |
| S | NVIDIA | minimaxai/minimax-m2 | ❌ Not in live API |
| A | Groq | meta-llama/llama-4-scout-17b-16e-preview | ❌ Not in live API |
| S | Groq | meta-llama/llama-4-maverick-17b-128e-preview | ❌ Not in live API |
| A | Groq | deepseek-r1-distill-llama-70b | ❌ Not in live API |
| A+ | Groq | qwen-qwq-32b | ❌ Not in live API |

These models are in our hardcoded list but **not available** in the live APIs.

### 3. "Is it time to ping and test them all?"

**Yes!** Let's do a comprehensive test. I've created tools to:
1. Check which models are obsolete
2. Actually ping test each model
3. Record results to database

## Commands

### Check for Obsolete Models
```bash
model-radar db obsolete
```

### Ping Test All Models
```bash
# Test first 20 models
model-radar db ping-test --limit 20

# Test all NVIDIA models
model-radar db ping-test --provider nvidia

# Test with higher concurrency
model-radar db ping-test --concurrency 10
```

## What We Found

### OpenRouter Free Tier Models
Our hardcoded list includes these **free** models (note the `:free` or `-free` suffix):
- `qwen/qwen3-coder:480b-free` - Qwen3 Coder 480B (S+)
- `mistralai/devstral-2-free` - Devstral 2 (S+)
- `mimo-v2-flash-free` - Mimo V2 Flash (A)
- `stepfun/step-3.5-flash:free` - Step 3.5 Flash (S+)
- `deepseek/deepseek-r1-0528:free` - DeepSeek R1 0528 (S)
- `qwen/qwen3-next-80b-a3b-instruct:free` - Qwen3 80B Instruct (S)
- `openai/gpt-oss-120b:free` - GPT OSS 120B (S)
- `openai/gpt-oss-20b:free` - GPT OSS 20B (A)
- `nvidia/nemotron-3-nano-30b-a3b:free` - Nemotron Nano 30B (A)
- `meta-llama/llama-3.3-70b-instruct:free` - Llama 3.3 70B (A-)

**But 4 of these are NOT in the live API!** They may have been deprecated.

### Live API Shows 486+ More Models
The live APIs show **548 total models** but we only have 62 hardcoded. That's **486 models we're missing!**

## Next Steps

### Option 1: Clean Up Obsolete Models
Remove the 9 obsolete models from hardcoded list:
```bash
# Check which are obsolete
model-radar db obsolete

# Then manually remove from providers.py
```

### Option 2: Auto-Update from Live APIs
Create a sync command that:
1. Fetches live models from APIs
2. Identifies new models
3. Adds them to database (with "unknown" tier initially)
4. Flags for manual review

### Option 3: Full Ping Test
Test ALL models to verify which actually work:
```bash
model-radar db ping-test --limit 100 --concurrency 10
```

This would:
- Mark working models as "available"
- Record latency for each
- Identify rate-limited models
- Update database with status

## Recommendation

**Do a full ping test** to get definitive answers:

1. Run ping test on all hardcoded models
2. Record results to database
3. Compare with live API results
4. Update hardcoded list to remove obsolete ones
5. Add new high-quality models from live APIs

This gives you a clean, verified list of models that actually work right now.
