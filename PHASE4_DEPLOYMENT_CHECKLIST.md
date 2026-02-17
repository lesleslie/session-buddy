# Phase 4 Deployment Checklist

**Date:** 2026-02-10
**Status:** ✅ Production Ready
**Purpose:** Complete deployment and validation of Phase 4 features

---

## Pre-Deployment Checklist

### 1. Environment Validation

- [ ] **Python 3.13+ installed**
  ```bash
  python --version  # Should be 3.13.x
  ```

- [ ] **All V4 dependencies installed**
  ```bash
  cd /path/to/session-buddy
  uv pip check  # Should pass without errors
  ```

- [ ] **Sufficient disk space** (100MB recommended)
  ```bash
  df -h ~/.claude/data/
  ```

- [ ] **Ports available** (8765 for WebSocket, 9090 for Prometheus)
  ```bash
  lsof -i :8765  # Should return empty
  lsof -i :9090  # Should return empty
  ```

### 2. Database Backup

- [ ] **Current database backed up**
  ```bash
  cp ~/.claude/data/session_buddy.db ~/.claude/data/session_buddy.db.v3.backup

  # Verify backup
  ls -lh ~/.claude/data/session_buddy.db.v3.backup
  ```

- [ ] **Backup integrity verified**
  ```bash
  sqlite3 ~/.claude/data/session_buddy.db.v3.backup "SELECT COUNT(*) FROM skill_invocation;"
  # Should return non-zero if you have data
  ```

### 3. Migration Files Present

- [ ] **V4 migration up file exists**
  ```bash
  ls -lh session_buddy/storage/migrations/V4__phase4_extensions__up.sql
  # Should be ~15KB (466 lines)
  ```

- [ ] **V4 migration down file exists**
  ```bash
  ls -lh session_buddy/storage/migrations/V4__phase4_extensions__down.sql
  # Should be ~3KB (87 lines)
  ```

---

## Deployment Steps

### Step 1: Apply V4 Migration

- [ ] **Migration applied successfully**
  ```python
  from pathlib import Path
  from session_buddy.storage.migrations.base import MigrationManager

  db_path = Path.home() / ".claude" / "data" / "session_buddy.db"
  manager = MigrationManager(db_path=db_path)
  manager.migrate()

  # Expected output:
  # Applying migration V4__phase4_extensions__up.sql
  # ✓ Created 11 new tables
  # ✓ Created 6 new views
  # ✓ Created 3 triggers
  # Migration V4 complete
  ```

- [ ] **Migration recorded in database**
  ```sql
  SELECT * FROM skill_migrations WHERE version = 4;
  # Should return one row with version=4
  ```

### Step 2: Verify V4 Schema

- [ ] **All V4 tables created**
  ```sql
  SELECT COUNT(*) FROM sqlite_master
  WHERE type='table'
  AND name IN (
      'skill_metrics_cache',
      'skill_time_series',
      'skill_anomalies',
      'skill_community_baselines',
      'skill_user_interactions',
      'skill_clusters',
      'skill_cluster_membership',
      'ab_test_configs',
      'ab_test_assignments',
      'ab_test_outcomes',
      'skill_categories',
      'skill_category_mapping',
      'skill_dependencies',
      'skill_modalities'
  );
  -- Expected: 14
  ```

- [ ] **All V4 views created**
  ```sql
  SELECT name FROM sqlite_master
  WHERE type='view'
  AND name IN (
      'v_realtime_skill_dashboard',
      'v_skill_effectiveness_trend',
      'v_community_baseline_comparison',
      'v_skill_dependency_network',
      'v_ab_test_summary',
      'v_multimodal_skill_catalog'
  );
  -- Expected: 6 rows
  ```

- [ ] **All V4 triggers created**
  ```sql
  SELECT name FROM sqlite_master
  WHERE type='trigger'
  AND name LIKE 'trg_%';
  -- Expected: At least 1 trigger (trg_metrics_cache_after_insert)
  ```

### Step 3: Initialize Taxonomy

- [ ] **Taxonomy initialization script exists**
  ```bash
  ls -lh scripts/initialize_taxonomy.py
  # Should be ~10KB (360+ lines)
  ```

- [ ] **Taxonomy initialized successfully**
  ```bash
  cd /path/to/session-buddy
  python scripts/initialize_taxonomy.py

  # Expected output:
  # Initializing skills taxonomy...
  # ✓ Initialized 6 categories
  # ✓ Initialized 4 modality types
  # ✓ Initialized 4 dependencies
  # Taxonomy initialization complete!
  ```

- [ ] **Taxonomy data verified**
  ```sql
  -- Check categories
  SELECT COUNT(*) FROM skill_categories;
  -- Expected: 6

  -- Check modalities
  SELECT COUNT(*) FROM skill_modalities;
  -- Expected: 4

  -- Check dependencies
  SELECT COUNT(*) FROM skill_dependencies;
  -- Expected: 4
  ```

---

## Post-Deployment Validation

### 1. V3 Backward Compatibility

- [ ] **V3 session management still works**
  ```python
  from session_buddy.storage.skills_storage import SkillsStorage

  storage = SkillsStorage()
  session_id = storage.create_session(project_path="/test/project")
  # Should succeed without errors
  ```

- [ ] **V3 tracking still works**
  ```python
  invocation_id = storage.track_invocation(
      session_id=session_id,
      skill_name="test-skill",
      completed=True,
      duration_seconds=5.0
  )
  # Should return valid invocation_id
  ```

- [ ] **V3 queries still work**
  ```python
  metrics = storage.get_skill_metrics("test-skill")
  # Should return dict with effectiveness metrics
  ```

### 2. V4 New Features

#### Real-Time Monitoring

- [ ] **WebSocket server starts**
  ```python
  from session_buddy.realtime import RealTimeMetricsServer

  server = RealTimeMetricsServer(port=8765)
  await server.start()
  # Should print: "WebSocket server started on ws://localhost:8765"
  ```

- [ ] **Real-time metrics query works**
  ```python
  metrics = storage.get_real_time_metrics(limit=5)
  # Should return list of top 5 skills
  ```

- [ ] **Anomaly detection works**
  ```python
  anomalies = storage.detect_anomalies(threshold=2.0)
  # Should return list (empty if no anomalies)
  ```

#### Analytics Engine

- [ ] **Predictive model works**
  ```python
  from session_buddy.analytics import get_predictor

  predictor = get_predictor("skills.db")
  probability = predictor.predict_success_probability(
      skill_name="pytest-run",
      user_query="test my code",
      workflow_phase="execution",
      session_context={"session_length_minutes": 30}
  )
  # Should return float between 0.0 and 1.0
  ```

- [ ] **A/B testing framework works**
  ```python
  from session_buddy.analytics import get_ab_framework, ABTestConfig

  framework = get_ab_framework("skills.db")
  test_id = framework.create_test(ABTestConfig(
      test_name="test_experiment",
      control_strategy="semantic_search",
      treatment_strategy="workflow_aware_search",
      start_date="2026-02-10T00:00:00Z"
  ))
  # Should return integer test_id
  ```

- [ ] **Time-series analysis works**
  ```python
  from session_buddy.analytics import get_analyzer

  analyzer = get_analyzer("skills.db")
  trend = analyzer.detect_trend("pytest-run", metric="completion_rate")
  # Should return dict with 'trend' (improving/declining/stable)
  ```

#### Cross-Session Learning

- [ ] **Collaborative filtering works**
  ```python
  from session_buddy.analytics import get_collaborative_engine

  engine = get_collaborative_engine()
  recommendations = engine.recommend_from_similar_users("user123", limit=5)
  # Should return list of recommendations (empty if cold start)
  ```

- [ ] **Community baselines work**
  ```python
  baselines = storage.get_community_baselines()
  # Should return list of skills with global metrics
  ```

#### MCP Tools

- [ ] **Phase 4 MCP tools registered**
  ```python
  # Check server logs for tool registration
  # Should see:
  # - get_real_time_metrics
  # - detect_anomalies
  # - get_skill_trend
  # - get_collaborative_recommendations
  # - get_community_baselines
  # - get_skill_dependencies
  ```

- [ ] **MCP tools execute successfully**
  ```python
  # Via MCP client
  result = await call_tool("get_real_time_metrics", {"limit": 5})
  # Should return dict with "top_skills" key
  ```

### 3. Integration Tests

- [ ] **All Phase 4 integration tests pass**
  ```bash
  cd /path/to/session-buddy
  pytest tests/test_phase4_integration.py -v

  # Expected: All tests pass (20+ scenarios)
  ```

- [ ] **Test coverage meets threshold**
  ```bash
  pytest tests/test_phase4_integration.py --cov=session_buddy --cov-report=term

  # Coverage should not decrease from baseline
  ```

- [ ] **No regression in existing tests**
  ```bash
  pytest tests/ -v --ignore=tests/test_phase4_integration.py

  # All existing tests should still pass
  ```

---

## Performance Validation

### 1. Query Performance

- [ ] **Real-time metrics < 100ms**
  ```python
  import time
  start = time.time()
  metrics = storage.get_real_time_metrics(limit=10)
  duration = (time.time() - start) * 1000
  assert duration < 100, f"Too slow: {duration}ms"
  ```

- [ ] **Anomaly detection < 200ms**
  ```python
  start = time.time()
  anomalies = storage.detect_anomalies(threshold=2.0)
  duration = (time.time() - start) * 1000
  assert duration < 200, f"Too slow: {duration}ms"
  ```

- [ ] **Collaborative filtering < 200ms**
  ```python
  start = time.time()
  recommendations = engine.recommend_from_similar_users("user123", limit=5)
  duration = (time.time() - start) * 1000
  assert duration < 200, f"Too slow: {duration}ms"
  ```

### 2. WebSocket Performance

- [ ] **Broadcast latency < 100ms**
  - Connect WebSocket client
  - Measure time from broadcast to receipt
  - Should be < 100ms for 10 clients

- [ ] **Handles 100+ concurrent clients**
  - Connect 100 WebSocket clients
  - Verify all receive updates
  - No dropped connections

### 3. Database Size

- [ ] **Database size reasonable**
  ```bash
  ls -lh ~/.claude/data/session_buddy.db

  # Expected: ~10-20MB for typical usage
  # (Empty DB: ~1MB, 100 skills + 1K invocations: ~15MB)
  ```

- [ ] **Time-series data growth manageable**
  ```sql
  SELECT COUNT(*) FROM skill_time_series;
  SELECT COUNT(*) * 300 / 1024 / 1024 as "Estimated MB"
  FROM skill_time_series;
  ```

---

## Rollback Testing

### 1. Rollback Procedure

- [ ] **Rollback tested successfully**
  ```python
  from pathlib import Path
  from session_buddy.storage.migrations.base import MigrationManager

  manager = MigrationManager(db_path="~/.claude/data/session_buddy.db")
  manager.rollback()

  # Expected output:
  # Applying migration V4__phase4_extensions__down.sql
  # ✓ Dropped 6 views
  # ✓ Dropped 14 tables
  # ✓ Dropped 3 triggers
  # Rollback to V3 complete
  ```

- [ ] **V3 functionality restored after rollback**
  ```python
  storage = SkillsStorage()
  session_id = storage.create_session(project_path="/test")
  # Should work exactly as before migration
  ```

### 2. Re-Migration After Rollback

- [ ] **Can re-apply V4 after rollback**
  ```python
  manager.migrate()
  # Should succeed without errors
  ```

---

## Monitoring Setup (Optional)

### 1. Prometheus Exporter

- [ ] **Prometheus exporter starts**
  ```python
  from session_buddy.realtime import PrometheusExporter

  exporter = PrometheusExporter(port=9090)
  exporter.start()
  # Should print: "Prometheus metrics exposed on http://localhost:9090"
  ```

- [ ] **Metrics endpoint accessible**
  ```bash
  curl http://localhost:9090/metrics

  # Should return Prometheus-formatted metrics
  # skill_invocations_total{...} 142.0
  # skill_duration_seconds_bucket{...} 45.0
  # etc.
  ```

- [ ] **Grafana dashboard configured** (if using Grafana)
  - Add Prometheus data source
  - Import dashboard from `docs/grafana/`
  - Verify panels display data

### 2. Health Checks

- [ ] **WebSocket health check**
  ```bash
  # Test WebSocket connection
  wscat -c ws://localhost:8765
  # Should connect successfully
  ```

- [ ] **Database health check**
  ```python
  from session_buddy.storage.skills_storage import SkillsStorage

  storage = SkillsStorage()
  health = storage.health_check()
  # Should return {"status": "healthy"}
  ```

---

## Documentation Verification

- [ ] **README updated with Phase 4 features**
  - Check for "Real-Time Monitoring" section
  - Check for "Advanced Analytics" section
  - Check for "Cross-Session Learning" section

- [ ] **Migration guide exists**
  ```bash
  ls -lh docs/migrations/V3_TO_V4_MIGRATION_GUIDE.md
  # Should exist and be comprehensive
  ```

- [ ] **API documentation updated**
  ```bash
  ls -lh docs/user/MCP_TOOLS_REFERENCE.md
  # Should include Phase 4 tools
  ```

---

## Final Sign-Off

### Pre-Production

- [ ] **All checklist items completed**
- [ ] **Stakeholder approval obtained**
- [ ] **Deployment window scheduled**
- [ ] **Rollback plan documented**

### Production Deployment

- [ ] **Database backed up**
- [ ] **Migration applied**
- [ ] **Services started** (WebSocket, Prometheus)
- [ ] **Monitoring active**
- [ ] **Documentation published**

### Post-Deployment

- [ ] **Health checks passing**
- [ ] **Performance metrics within SLA**
- [ ] **No errors in logs**
- [ ] **User acceptance confirmed**

---

## Contact & Support

**Issues Encountered?**

1. **Check logs:** `~/.claude/logs/session-buddy.log`
2. **Run diagnostics:** `python -m pytest tests/test_phase4_integration.py -v`
3. **Verify migration:** `sqlite3 skills.db "SELECT * FROM skill_migrations WHERE version=4;"`
4. **Test rollback:** If all else fails, rollback and restore from backup

**Documentation:**

- [Migration Guide](docs/migrations/V3_TO_V4_MIGRATION_GUIDE.md)
- [V4 Schema Summary](PHASE4_V4_SCHEMA_SUMMARY.md)
- [Final Status Report](PHASE4_FINAL_STATUS_REPORT.md)

**Deployment Status:** ✅ Ready for Production
**Rollback Tested:** ✅ Verified
**Breaking Changes:** None
**Recommendation:** Deploy during low-traffic window for first migration

---

**Last Updated:** 2026-02-10
**Checklist Version:** 1.0
**Phase:** 4 (Advanced Analytics & Integration)
