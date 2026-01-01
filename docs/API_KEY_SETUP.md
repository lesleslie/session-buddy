# API Key Setup

Memori-inspired features support multiple LLM providers. All keys are optional; the system gracefully degrades to pattern-based extraction when no providers are available.

## Providers

- OpenAI: set `OPENAI_API_KEY`
- Anthropic: set `ANTHROPIC_API_KEY`
- Google Gemini: set `GEMINI_API_KEY` (or `GOOGLE_API_KEY`)
- Ollama: no API key required; ensure the service is running locally

## Feature Flags (env overrides)

Defaults are now ON; set to `false` to stage/disable selectively:

- `SESSION_BUDDY_USE_SCHEMA_V2`
- `SESSION_BUDDY_ENABLE_LLM_ENTITY_EXTRACTION`
- `SESSION_BUDDY_ENABLE_ANTHROPIC`
- `SESSION_BUDDY_ENABLE_OLLAMA`
- `SESSION_BUDDY_ENABLE_CONSCIOUS_AGENT`
- `SESSION_BUDDY_ENABLE_FILESYSTEM_EXTRACTION`

Example:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export SESSION_BUDDY_ENABLE_LLM_ENTITY_EXTRACTION=true  # or 'false' to disable temporarily
export SESSION_BUDDY_ENABLE_ANTHROPIC=true              # or 'false' to disable temporarily
```
