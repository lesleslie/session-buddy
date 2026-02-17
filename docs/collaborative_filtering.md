# Collaborative Filtering Engine

## Overview

The `CollaborativeFilteringEngine` provides user-based collaborative filtering for skill recommendations in Session-Buddy. It analyzes user-skill interactions to find users with similar usage patterns and recommends skills based on what similar users used successfully.

## Algorithm

### User Similarity Calculation

Uses **Jaccard similarity** to measure how similar two users are:

```
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

Where:
- `A` = set of skills used by user A (completed)
- `B` = set of skills used by user B (completed)
- `|A ∩ B|` = number of common skills (intersection)
- `|A ∪ B|` = number of unique skills across both users (union)

**Example:**
- User1 used skills: {pytest, ruff, mypy, black}
- User2 used skills: {pytest, ruff, pylint}
- Common skills: {pytest, ruff} = 2
- All skills: {pytest, ruff, mypy, black, pylint} = 5
- Jaccard similarity: 2/5 = 0.4 (40%)

### Recommendation Scoring

Combines user similarity with skill success rate:

```
recommendation_score = user_similarity × skill_completion_rate
```

Where:
- `user_similarity` = Jaccard similarity (0.0 to 1.0)
- `skill_completion_rate` = success rate for similar user (0.0 to 1.0)

**Example:**
- User similarity: 0.8 (80%)
- Skill completion rate: 0.9 (90%)
- Recommendation score: 0.8 × 0.9 = 0.72 (72%)

## Features

### 1. User Similarity Discovery

Find users with similar skill usage patterns:

```python
from session_buddy.analytics import CollaborativeFilteringEngine

engine = CollaborativeFilteringEngine("skills.db")

# Find similar users
similar_users = engine.get_similar_users(
    user_id="user123",
    min_common_skills=3,  # At least 3 common skills
    limit=10              # Top 10 similar users
)

for user_id, similarity in similar_users:
    print(f"User {user_id}: {similarity:.1%} similarity")
```

**Output:**
```
User user456: 75.0% similarity
User user789: 60.0% similarity
User user012: 50.0% similarity
```

### 2. Skill Recommendations

Generate personalized recommendations based on similar users:

```python
recommendations = engine.recommend_from_similar_users(
    user_id="user123",
    limit=5,                # Top 5 recommendations
    min_common_skills=3     # Minimum common skills threshold
)

for rec in recommendations:
    print(f"{rec['skill_name']}: {rec['score']:.2f} "
          f"(completion: {rec['completion_rate']:.1%})")
```

**Output:**
```
semantic-search: 0.68 (completion: 90.0%)
code-refactor: 0.55 (completion: 73.3%)
test-generator: 0.45 (completion: 75.0%)
```

### 3. Community Baselines

Update global skill effectiveness metrics:

```python
result = engine.update_community_baselines()
print(f"Updated {result['skills_updated']} skill baselines")
```

This aggregates across all users to create:
- Global completion rates
- Average duration
- Effectiveness percentiles
- Most common workflow phases

### 4. Fallback Recommendations

Handle cold start problem with global popularity:

```python
# When no similar users exist, fall back to popular skills
fallback = engine.get_global_fallback_recommendations(
    limit=5,
    min_invocations=10  # At least 10 uses
)

for rec in fallback:
    print(f"{rec['skill_name']}: "
          f"{rec['effectiveness_percentile']:.0f}th percentile")
```

### 5. User Profiling

Get user's skill usage profile:

```python
profile = engine.get_user_skill_profile("user123")

print(f"Unique skills: {profile['unique_skills']}")
print(f"Total interactions: {profile['total_interactions']}")
print(f"Completion rate: {profile['completion_rate']:.1%}")
print(f"Top skills: {profile['top_skills'][:5]}")
```

## API Reference

### `CollaborativeFilteringEngine`

Main class for collaborative filtering.

#### Constructor

```python
CollaborativeFilteringEngine(
    db_path: str | Path,
    cache_ttl_seconds: int = 3600
)
```

**Parameters:**
- `db_path`: Path to SQLite database
- `cache_ttl_seconds`: Cache TTL for similar users (default: 1 hour)

#### Methods

##### `get_similar_users()`

```python
get_similar_users(
    user_id: str,
    min_common_skills: int = 3,
    limit: int = 10
) -> list[tuple[str, float]]
```

Find users with similar skill usage patterns.

**Returns:** List of `(user_id, jaccard_similarity)` tuples

##### `recommend_from_similar_users()`

```python
recommend_from_similar_users(
    user_id: str,
    limit: int = 5,
    min_common_skills: int = 3
) -> list[dict[str, object]]
```

Generate personalized recommendations.

**Returns:** List of recommendation dictionaries:
```python
{
    "skill_name": str,
    "score": float,
    "completion_rate": float,
    "source": "collaborative_filtering",
    "similar_user_id": str
}
```

##### `update_community_baselines()`

```python
update_community_baselines() -> dict[str, object]
```

Update global skill effectiveness baselines.

**Returns:** Update status dictionary:
```python
{
    "status": "updated",
    "timestamp": str,
    "skills_updated": int
}
```

##### `get_global_fallback_recommendations()`

```python
get_global_fallback_recommendations(
    limit: int = 5,
    min_invocations: int = 10
) -> list[dict[str, object]]
```

Get globally popular skills for cold start.

##### `get_user_skill_profile()`

```python
get_user_skill_profile(user_id: str) -> dict[str, object]
```

Get user's skill usage profile.

##### `clear_cache()`

```python
clear_cache() -> None
```

Clear cached similar users calculations.

## Database Schema

The engine uses the V4 Phase 4 schema tables:

### `skill_user_interactions`

Stores user-skill interaction matrix:

```sql
CREATE TABLE skill_user_interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,          -- Anonymous user identifier (hashed)
    session_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    invoked_at TEXT NOT NULL,
    completed BOOLEAN NOT NULL,     -- Success/failure
    rating REAL,                    -- Optional user feedback (1-5)
    alternatives_considered TEXT    -- JSON array
);
```

**Indexes:**
- `(user_id, invoked_at DESC)` - User history queries
- `(skill_name, completed)` - Skill performance queries
- `session_id` - Session analysis

### `skill_community_baselines`

Stores aggregated skill effectiveness:

```sql
CREATE TABLE skill_community_baselines (
    skill_name TEXT PRIMARY KEY,
    total_users INTEGER DEFAULT 0,
    total_invocations INTEGER DEFAULT 0,
    global_completion_rate REAL,
    global_avg_duration_seconds REAL,
    most_common_workflow_phase TEXT,
    effectiveness_percentile REAL,   -- 0-100
    last_updated TEXT NOT NULL
);
```

## Performance Considerations

### Caching Strategy

The engine implements two-level caching:

1. **Similar Users Cache** (TTL: 1 hour)
   - Key: `user_id:min_common_skills:limit`
   - Value: List of similar users with similarity scores
   - Reduces expensive Jaccard calculations

2. **Recommendation Cache** (implicit via similar users cache)
   - Recommendations depend on similar users
   - Benefits from similar users cache

### SQL Optimization

Uses efficient SQL patterns:

1. **Jaccard Similarity in SQL**
   ```sql
   SELECT
       user_id,
       CAST(common_skills AS REAL) /
       (total_skills + ? - common_skills) as jaccard_similarity
   FROM other_user_skills
   ```

2. **Subquery Filtering**
   - Filters users before similarity calculation
   - Reduces result set size

3. **Indexed Queries**
   - All queries use indexed columns
   - Optimized for large datasets

### Complexity Analysis

| Operation | Time Complexity | Notes |
|-----------|----------------|-------|
| Find similar users | O(n × k) | n = users, k = avg skills per user |
| Generate recommendations | O(m × p) | m = similar users, p = skills per user |
| Update baselines | O(s) | s = total skills |
| Get user profile | O(k) | k = user's skills |

## Privacy & Security

### User Anonymization

All user IDs are hashed using SHA-256:

```python
def _hash_user_id(self, user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()
```

**Benefits:**
- User IDs cannot be reverse-engineered
- Consistent hashing (same user = same hash)
- No personal data stored

### Data Isolation

- Each query filters by user ID
- No cross-user data leakage
- Anonymous user identifiers only

## Cold Start Problem

The cold start problem occurs when:
1. New user has no skill history
2. No similar users can be found
3. Cannot generate personalized recommendations

### Solution: Fallback to Global Popularity

```python
# Try personalized recommendations first
recommendations = engine.recommend_from_similar_users("new_user")

if not recommendations:
    # Fall back to global popularity
    recommendations = engine.get_global_fallback_recommendations()
```

Global recommendations use:
- Community-wide completion rates
- Effectiveness percentiles
- Minimum invocation threshold

## Usage Examples

### Basic Workflow

```python
from session_buddy.analytics import get_collaborative_engine

# Get engine (uses default path)
engine = get_collaborative_engine()

# Update community baselines (do this periodically)
engine.update_community_baselines()

# Get recommendations for user
recommendations = engine.recommend_from_similar_users("user123", limit=5)

# Display recommendations
for rec in recommendations:
    print(f"{rec['skill_name']}: {rec['score']:.2f}")
```

### Integration with Recommendation Pipeline

```python
from session_buddy.analytics import (
    get_collaborative_engine,
    SkillSuccessPredictor,
    get_predictor
)

# Get both engines
cf_engine = get_collaborative_engine()
pred_engine = get_predictor()

# Get collaborative filtering recommendations
cf_recs = cf_engine.recommend_from_similar_users("user123", limit=5)

# Get ML-based predictions
# (assuming you have a session context)
prob = pred_engine.predict_success_probability(
    skill_name="semantic-search",
    user_query="Find similar code patterns",
    workflow_phase="execution",
    session_context=context
)

# Combine or rank recommendations
# (implementation depends on your use case)
```

### Batch Processing

```python
# Update baselines for all users
engine.update_community_baselines()

# Get user profiles for analysis
users = ["user1", "user2", "user3"]

for user_id in users:
    profile = engine.get_user_skill_profile(user_id)
    print(f"{user_id}: {profile['unique_skills']} skills")

    # Get recommendations
    recommendations = engine.recommend_from_similar_users(user_id)
    print(f"  Recommendations: {len(recommendations)}")
```

## Testing

Run tests:

```bash
# Run all collaborative filtering tests
pytest tests/test_collaborative_filtering.py -v

# Run specific test
pytest tests/test_collaborative_filtering.py::TestCollaborativeFilteringEngine::test_get_similar_users_basic -v

# With coverage
pytest tests/test_collaborative_filtering.py --cov=session_buddy.analytics.collaborative_filtering
```

## Limitations & Future Improvements

### Current Limitations

1. **Sparsity Problem**: Requires minimum common skills threshold
2. **Popularity Bias**: Favors popular skills over niche ones
3. **Cold Start**: Relies on fallback for new users
4. **Scalability**: O(n²) similarity calculation for large user bases

### Potential Improvements

1. **Item-Based Filtering**: Also recommend based on skill similarity
2. **Matrix Factorization**: Use SVD or ALS for better scalability
3. **Hybrid Approach**: Combine with content-based filtering
4. **Temporal Weighting**: Weight recent interactions higher
5. **Context Awareness**: Consider workflow phase, project type
6. **Diversity**: Ensure diverse skill recommendations

## References

- [Collaborative Filtering Wikipedia](https://en.wikipedia.org/wiki/Collaborative_filtering)
- [Jaccard Index Wikipedia](https://en.wikipedia.org/wiki/Jaccard_index)
- [Recommender Systems Handbook](https://www.amazon.com/Recommender-Systems-Handbook-Technologies-Applications/dp/1481422604)

## Contributing

When contributing to the collaborative filtering engine:

1. **Maintain privacy**: Always hash user IDs
2. **Handle cold start**: Provide fallback recommendations
3. **Cache aggressively**: Similarity calculations are expensive
4. **Test thoroughly**: Use realistic test data
5. **Document changes**: Update this README with algorithm changes

## License

Part of the Session-Buddy project. See project LICENSE for details.
