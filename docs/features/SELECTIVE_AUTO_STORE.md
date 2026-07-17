---
status: complete
role: canonical
date: 2026-07-16
last_reviewed: 2026-07-16
superseded_by: null
blocks_on: []
topic: lifecycle
---

# Selective Auto-Store Implementation

## Overview

This document describes the implementation of selective automatic reflection storage at checkpoints, designed to maintain high signal-to-noise ratio in the memory system while capturing meaningful insights.

## Implementation Date

2025-09-30

## Problem Statement

Previously, the checkpoint system would either:

1. Always store reflections (creating noise and storage bloat)
1. Never store reflections automatically (losing valuable context)

This created a dilemma:

- **Too much auto-storage** → Memory search becomes ineffective due to noise
- **Too little auto-storage** → Valuable insights get lost

## Solution: Selective Auto-Store with Intelligent Triggers

### Architecture

The implementation uses a decision-based approach with configurable thresholds:

```
┌─────────────────────────────────────────────────┐
│         Checkpoint Triggered                     │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│   should_auto_store_checkpoint()                 │
│   • Analyze quality score & history              │
│   • Check trigger conditions                     │
│   • Return AutoStoreDecision                     │
└─────────────────┬───────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
   Should Store         Should Skip
        │                   │
        ▼                   ▼
┌───────────────┐    ┌──────────────┐
│ Store with    │    │ Log skip     │
│ semantic tags │    │ reason       │
└───────────────┘    └──────────────┘
```

### Key Components

#### 1. Decision Logic (`utils/reflection_utils.py`)

**Core Function:**

```python
def should_auto_store_checkpoint(
    quality_score: int,
    previous_score: int | None = None,
    is_manual: bool = False,
    session_phase: str = "checkpoint",
) -> AutoStoreDecision
```

**Auto-Store Triggers:**

- **Manual Checkpoints**: Always stored (user explicitly requested)
- **Session End**: Always stored (final state capture)
- **Significant Quality Changes**: Delta ≥10 points (configurable)
- **Exceptional Quality**: Score ≥90/100 (configurable)

**Skip Conditions:**

- Routine automatic checkpoints with minimal changes
- Quality changes below threshold (default: \<10 points)
- Auto-store globally disabled

#### 2. Configuration (`config.py`)

```python
class SessionConfig(BaseModel):
    enable_auto_store_reflections: bool = True
    auto_store_quality_delta_threshold: int = 10  # Min delta
    auto_store_exceptional_quality_threshold: int = 90  # Exceptional
    auto_store_manual_checkpoints: bool = True
    auto_store_session_end: bool = True
```

#### 3. Quality History Tracking (`core/session_manager.py`)

The `SessionLifecycleManager` now tracks quality history:

```python
class SessionLifecycleManager:
    def __init__(self):
        self._quality_history: dict[str, list[int]] = {}

    def get_previous_quality_score(self, project: str) -> int | None
    def record_quality_score(self, project: str, score: int) -> None
```

Maintains last 10 scores per project for trend analysis.

#### 4. Integration (`tools/session_tools.py`)

The checkpoint tool now:

1. Calls `checkpoint_session(is_manual=True)` for explicit checkpoints
1. Receives `AutoStoreDecision` in response
1. Stores reflection with semantic tags if decision is positive
1. Shows user-friendly message explaining the decision

### Semantic Tagging System

Auto-stored reflections get meaningful, searchable tags:

**Base Tags:**

- `checkpoint`, `auto-stored`, `{reason}`

**Quality Tags:**

- `high-quality` (≥90)
- `good-quality` (≥75)
- `needs-improvement` (\<60)

**Context Tags:**

- `manual_checkpoint`, `session_end`
- `quality_improvement`, `quality_degradation`
- `user-initiated`, `quality-change`, `session-summary`

**Project Tag:**

- Project name for filtering

### User Experience

#### When Auto-Store Triggers:

```
💾 Manual checkpoint - reflection stored automatically (quality: 85/100)
```

#### When Skipped:

```
⏭️ Routine checkpoint - reflection storage skipped (maintains high signal-to-noise ratio)
```

#### Quality Improvements:

```
📈 Quality improved significantly - reflection stored (quality: 85/100, +15 points)
```

## Testing

Comprehensive test suite in `tests/unit/test_reflection_utils.py`:

- 25 test cases covering all decision paths
- 94.79% code coverage
- Tests for configuration integration
- Integration test patterns for full checkpoint flow

## Benefits

### 1. **High Signal-to-Noise Ratio**

Only meaningful checkpoints are stored, making searches more effective.

### 2. **Zero Configuration Burden**

Smart defaults work out of the box, but power users can tune thresholds.

### 3. **Semantic Search Enhancement**

Rich tagging enables precise filtering:

```python
# Find all quality improvements in project X
await db.search_reflections("quality_improvement project-x")

# Find manual checkpoints with high quality
await db.search_reflections("user-initiated high-quality")
```

### 4. **Storage Efficiency**

Prevents database bloat from routine checkpoints.

### 5. **Transparent Decision-Making**

Users always see why storage happened or was skipped.

## Configuration Examples

### Conservative (Less Storage)

```python
auto_store_quality_delta_threshold: int = 15  # Stricter delta
auto_store_exceptional_quality_threshold: int = 95  # Higher bar
```

### Aggressive (More Storage)

```python
auto_store_quality_delta_threshold: int = 5  # Lower delta
auto_store_exceptional_quality_threshold: int = 85  # Lower bar
```

### Manual-Only

```python
enable_auto_store_reflections: bool = True
auto_store_manual_checkpoints: bool = True
auto_store_session_end: bool = True
auto_store_quality_delta_threshold: int = 100  # Effectively disable quality triggers
```

## Performance Considerations

### Memory Overhead

- Quality history limited to 10 scores per project
- O(1) lookup for previous scores
- Minimal computational cost for decision logic

### Storage Impact

With default configuration, expect:

- ~5-10 reflections per day for active development
- ~1-2 reflections per day for routine work
- Previous behavior would have stored ~50-100/day

## Future Enhancements

### Potential Improvements

1. **AI-Powered Decisions**: Use LLM to analyze checkpoint significance
1. **User Feedback Loop**: Learn from which reflections are actually searched
1. **Project-Specific Thresholds**: Different settings per project type
1. **Time-Based Decay**: Adjust thresholds based on session duration

### Extension Points

- `CheckpointReason` enum easily extensible
- Configuration system supports new thresholds
- Decision logic isolated for easy modification

## Migration Notes

### Existing Installations

- No migration required - feature is additive
- Old reflections remain searchable with existing tags
- New behavior applies to all future checkpoints

### Rollback

To disable the feature:

```python
enable_auto_store_reflections: bool = False
```

## Related Files

### Core Implementation

- `session_buddy/utils/reflection_utils.py` - Decision logic
- `session_buddy/config.py` - Configuration
- `session_buddy/core/session_manager.py` - Quality tracking
- `session_buddy/tools/session_tools.py` - Integration

### Tests

- `tests/unit/test_reflection_utils.py` - Unit tests

### Documentation

- `CLAUDE.md` - Updated with selective auto-store section
- This document

## Conclusion

The selective auto-store implementation successfully balances:

- **Proactive intelligence**: Captures important moments automatically
- **User control**: Transparent decisions with configurable thresholds
- **Signal-to-noise ratio**: Only meaningful reflections are stored

This ensures the memory system remains a valuable tool for long-term context retention without becoming cluttered with routine checkpoints.
