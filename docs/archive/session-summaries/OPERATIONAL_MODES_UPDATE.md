# README Update: Add Operational Modes Section

Add this section after the "Features" section in the README.md:

---

## 🚀 Operational Modes

Session-Buddy now supports **two operational modes** to accommodate different use cases:

### ⚡ Lite Mode (NEW!)

**Zero-dependency, in-memory mode for testing and CI/CD**

```bash
session-buddy --mode=lite start
# or
SESSION_BUDDY_MODE=lite session-buddy start
```

**Characteristics:**
- ⚡ In-memory database (`:memory:`)
- 📦 No external dependencies
- ⏱️ Fast startup (< 2 seconds)
- 🧪 Perfect for testing and CI/CD

**Trade-offs:**
- ❌ No data persistence (ephemeral)
- ❌ No semantic search (embeddings disabled)
- ❌ No multi-project coordination

### 💾 Standard Mode (Default)

**Full-featured production mode with persistent storage**

```bash
session-buddy start  # Default mode
# or
session-buddy --mode=standard start
```

**Characteristics:**
- 💾 Persistent database (`~/.claude/data/reflection.duckdb`)
- 📦 Full feature set
- 🧠 Semantic search enabled
- 🌐 Multi-project coordination

**Ideal For:**
- ✅ Daily development
- ✅ Production deployments
- ✅ Knowledge base building

### Quick Comparison

| Feature | Lite Mode | Standard Mode |
|---------|-----------|---------------|
| **Setup Time** | < 2 min | ~ 5 min |
| **Persistence** | No (ephemeral) | Yes (persistent) |
| **Database** | `:memory:` | `~/.claude/data/reflection.duckdb` |
| **Embeddings** | Disabled | Enabled |
| **Ideal For** | Testing, CI/CD | Development, Production |

**📖 See [Operational Modes Guide](docs/guides/operational-modes.md) for complete documentation.**

---

Then update the "Usage" section to include mode selection:

---

## Usage

### Starting Session-Buddy

```bash
# Start in standard mode (default)
session-buddy start

# Start in lite mode (fast, no persistence)
session-buddy --mode=lite start

# Using environment variable
SESSION_BUDDY_MODE=lite session-buddy start

# Using startup script
./scripts/dev-start.sh lite
```

---

Then update the "Installation" section:

---

## Installation

### Quick Start (Standard Mode)

```bash
# Clone and install
git clone https://github.com/lesleslie/session-buddy.git
cd session-buddy
uv pip install -e .

# Start in standard mode
session-buddy start
```

### Quick Start (Lite Mode)

```bash
# Clone and install
git clone https://github.com/lesleslie/session-buddy.git
cd session-buddy
uv pip install -e .

# Start in lite mode (no persistence, fast startup)
session-buddy --mode=lite start
```

### Development Setup

```bash
# Install with dev dependencies
uv sync --group dev

# Run tests
pytest

# Start in lite mode for development
./scripts/dev-start.sh lite
```

---

Finally, add to the "Documentation" section:

---

### Operational Modes

- **[Operational Modes Guide](docs/guides/operational-modes.md)** ⭐ **NEW**
  - Lite mode vs standard mode
  - Mode selection and configuration
  - Migration guide
  - Best practices

---
