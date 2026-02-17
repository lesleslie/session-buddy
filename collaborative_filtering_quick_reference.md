# Collaborative Filtering - Quick Reference

## Installation

The collaborative filtering engine is part of Session-Buddy Phase 4.

```python
from session_buddy.analytics import get_collaborative_engine

# Initialize with default path
engine = get_collaborative_engine()

# Or specify custom path
from pathlib import Path
engine = get_collaborative_engine(Path("custom/path/skills.db"))
```

## Quick Start

```python
# 1. Update community baselines (do this periodically)
result = engine.update_community_baselines()
print(f"Updated {result['skills_updated']} skills")

# 2. Get recommendations for a user
recommendations = engine.recommend_from_similar_users("user123", limit=5)

for rec in recommendations:
    print(f"{rec['skill_name']}: {rec['score']:.2f} "
          f"(success: {rec['completion_rate']:.1%})")

# 3. Handle cold start
if not recommendations:
    # Fall back to global popularity
    fallback = engine.get_global_fallback_recommendations(limit=5)
    recommendations = fallback
```

## API Cheat Sheet

### Find Similar Users

```python
similar_users = engine.get_similar_users(
    user_id="user123",
    min_common_skills=3,  # Minimum shared skills
    limit=10              # Max results
)

# Returns: [(user_id, jaccard_similarity), ...]
# Example: [("user456", 0.75), ("user789", 0.60), ...]
```

### Get Recommendations

```python
recommendations = engine.recommend_from_similar_users(
    user_id="user123",
    limit=5,                # Max recommendations
    min_common_skills=3     # Similarity threshold
)

# Returns: [{
#     "skill_name": "semantic-search",
#     "score": 0.72,
#     "completion_rate": 0.90,
#     "source": "collaborative_filtering",
#     "similar_user_id": "user456"
# }, ...]
```

### Update Community Baselines

```python
result = engine.update_community_baselines()

# Returns: {
#     "status": "updated",
#     "timestamp": "2025-02-10T12:00:00",
#     "skills_updated": 42
# }
```

### Get User Profile

```python
profile = engine.get_user_skill_profile("user123")

# Returns: {
#     "user_id": "user123",
#     "unique_skills": 15,
#     "total_interactions": 47,
#     "completion_rate": 0.85,
#     "top_skills": [("pytest", 10), ("ruff", 8), ...]
# }
```

### Fallback Recommendations

```python
fallback = engine.get_global_fallback_recommendations(
    limit=5,
    min_invocations=10  # Minimum usage threshold
)

# Returns: [{
#     "skill_name": "pytest",
#     "score": 0.95,
#     "completion_rate": 0.92,
#     "source": "global_popularity",
#     "effectiveness_percentile": 95.0
# }, ...]
```

### Cache Management

```python
# Clear cached similar users
engine.clear_cache()

# Cache TTL is set during initialization
engine = CollaborativeFilteringEngine(
    db_path="skills.db",
    cache_ttl_seconds=3600  # 1 hour
)
```

## Algorithm Overview

### Jaccard Similarity

```
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

Measures how similar two users' skill sets are.

**Example:**
- User1: {pytest, ruff, mypy}
- User2: {pytest, ruff, pylint}
- Similarity: 2/4 = 0.5 (50%)

### Recommendation Score

```
score = user_similarity × skill_completion_rate
```

Combines similarity with skill success rate.

**Example:**
- User similarity: 0.80
- Completion rate: 0.90
- Score: 0.72 (72%)

## Common Patterns

### Pattern 1: Personalized Recommendations

```python
def get_user_recommendations(user_id: str, limit: int = 5):
    """Get personalized recommendations with fallback."""
    engine = get_collaborative_engine()

    # Try collaborative filtering
    recommendations = engine.recommend_from_similar_users(user_id, limit)

    # Fall back to global popularity if needed
    if not recommendations:
        recommendations = engine.get_global_fallback_recommendations(limit)

    return recommendations
```

### Pattern 2: Batch Processing

```python
def update_all_users(user_ids: list[str]):
    """Update recommendations for multiple users."""
    engine = get_collaborative_engine()
    engine.update_community_baselines()

    for user_id in user_ids:
        profile = engine.get_user_skill_profile(user_id)
        recs = engine.recommend_from_similar_users(user_id)
        print(f"{user_id}: {profile['unique_skills']} skills, "
              f"{len(recs)} recommendations")
```

### Pattern 3: Similarity Analysis

```python
def analyze_user_similarity(user_id: str):
    """Analyze which users are most similar."""
    engine = get_collaborative_engine()

    similar = engine.get_similar_users(user_id, min_common_skills=3, limit=10)

    print(f"Users similar to {user_id}:")
    for similar_id, similarity in similar:
        print(f"  {similar_id}: {similarity:.1%}")
```

### Pattern 4: Cold Start Detection

```python
def is_cold_start_user(user_id: str) -> bool:
    """Check if user is a cold start (no history)."""
    engine = get_collaborative_engine()

    profile = engine.get_user_skill_profile(user_id)
    return profile['unique_skills'] == 0
```

## Performance Tips

1. **Use caching**: Similarity calculations are cached for 1 hour
2. **Batch updates**: Update community baselines periodically, not on every request
3. **Limit results**: Use `limit` parameter to avoid large result sets
4. **Set appropriate thresholds**: `min_common_skills` affects performance

## Testing

```python
# Test the engine
engine = get_collaborative_engine()

# Test 1: Find similar users
similar = engine.get_similar_users("test_user", min_common_skills=1)
assert len(similar) >= 0

# Test 2: Get recommendations
recs = engine.recommend_from_similar_users("test_user", limit=3)
assert len(recs) <= 3

# Test 3: Update baselines
result = engine.update_community_baselines()
assert result["status"] == "updated"

print("✓ All tests passed")
```

## Troubleshooting

### Problem: No similar users found

**Cause:** User has no skill history or `min_common_skills` too high

**Solution:**
```python
# Lower threshold
similar = engine.get_similar_users(user_id, min_common_skills=1)

# Or use fallback
if not similar:
    fallback = engine.get_global_fallback_recommendations()
```

### Problem: Empty recommendations

**Cause:** Cold start or all similar users' skills already tried

**Solution:** Always have fallback logic
```python
recommendations = engine.recommend_from_similar_users(user_id)
if not recommendations:
    recommendations = engine.get_global_fallback_recommendations()
```

### Problem: Slow performance

**Cause:** Large user base, no caching

**Solution:**
```python
# Increase cache TTL
engine = CollaborativeFilteringEngine(
    db_path="skills.db",
    cache_ttl_seconds=7200  # 2 hours
)

# Or pre-warm cache
engine.get_similar_users(user_id)  # First call caches result
```

## Database Requirements

Engine requires V4 Phase 4 schema:

```sql
-- User-skill interactions
CREATE TABLE skill_user_interactions (
    user_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    completed BOOLEAN NOT NULL,
    ...
);

-- Community baselines
CREATE TABLE skill_community_baselines (
    skill_name TEXT PRIMARY KEY,
    global_completion_rate REAL,
    effectiveness_percentile REAL,
    ...
);
```

## Privacy Notes

- All user IDs are hashed with SHA-256
- No personal data stored
- Anonymous identifiers only
- Hash is one-way (cannot reverse)

## Further Reading

- Full documentation: `docs/collaborative_filtering.md`
- Implementation details: `COLLABORATIVE_FILTERING_IMPLEMENTATION.md`
- Test suite: `tests/test_collaborative_filtering.py`
- V4 schema: `session_buddy/storage/migrations/V4__phase4_extensions__up.sql`

## Support

For issues or questions:
1. Check documentation in `docs/collaborative_filtering.md`
2. Review test cases in `tests/test_collaborative_filtering.py`
3. Examine source code in `session_buddy/analytics/collaborative_filtering.py`
