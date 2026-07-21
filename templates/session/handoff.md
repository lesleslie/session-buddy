______________________________________________________________________

## status: active role: canonical date: 2026-07-16 last_reviewed: 2026-07-16 superseded_by: null blocks_on: [] topic: plugin-standardization

# Session Handoff - {{ project_name }}

**Session ID**: `{{ session_id }}`
**Started**: {{ session_start|datetime("%Y-%m-%d %H:%M:%S") }}
**Ended**: {{ session_end|datetime("%Y-%m-%d %H:%M:%S") }}
**Duration**: {{ duration_minutes }} minutes
**Quality Score**: {{ quality_score }}/100

______________________________________________________________________

## Executive Summary

{{ summary }}

______________________________________________________________________

## Session Metrics

### Quality Assessment

- **Overall Score**: {{ quality_score }}/100
- **Quality Change**: {{ quality_delta }} points ({{ "improved" if quality_delta > 0 else "declined" if quality_delta < 0 else "stable" }})
  {% if quality_factors %}
- **Key Factors**:
  {% for factor, score in quality_factors.items() %}
  - {{ factor }}: {{ score }}/100
    {% endfor %}
    {% endif %}

### Activity Metrics

{% if metrics %}

- **Total Checkpoints**: {{ metrics.get('checkpoint_count', 0) }}
- **Files Modified**: {{ metrics.get('files_modified', 0) }}
- **Lines Added**: {{ metrics.get('lines_added', 0) }}
- **Lines Removed**: {{ metrics.get('lines_removed', 0) }}
  {% if metrics.get('test_runs') %}
- **Test Runs**: {{ metrics.test_runs }}
  - Passed: {{ metrics.get('tests_passed', 0) }}
  - Failed: {{ metrics.get('tests_failed', 0) }}
    {% endif %}
    {% endif %}

______________________________________________________________________

## Work Completed

{% if completed_tasks %}

### Tasks Accomplished

{% for task in completed_tasks %}

- {{ task }}
  {% endfor %}
  {% else %}
  _No tasks explicitly tracked in this session._
  {% endif %}

### Files Modified

{% if modified_files %}
{% for file in modified_files %}

- `{{ file.path }}`{% if file.changes %} ({{ file.changes }}){% endif %}
  {% endfor %}
  {% else %}
  _No files modified in this session._
  {% endif %}

______________________________________________________________________

## Technical Details

### Checkpoints

{% if checkpoints %}
{% for checkpoint in checkpoints %}

#### Checkpoint {{ loop.index }} - {{ checkpoint.timestamp|datetime("%H:%M:%S") }}

- **Quality**: {{ checkpoint.quality_score }}/100
- **Summary**: {{ checkpoint.summary }}
  {% if checkpoint.key_changes %}
- **Key Changes**:
  {% for change in checkpoint.key_changes %}
  - {{ change }}
    {% endfor %}
    {% endif %}
    {% endfor %}
    {% else %}
    _No checkpoints recorded in this session._
    {% endif %}

### Git Activity

{% if git_commits %}
**Commits Made**:
{% for commit in git_commits %}

- {{ commit.hash[:7] }} - {{ commit.message }}
  {% endfor %}
  {% else %}
  _No Git commits made in this session._
  {% endif %}

______________________________________________________________________

## Next Steps & Recommendations

{% if recommendations %}

### Recommended Actions

{% for rec in recommendations %}
{{ loop.index }}. **{{ rec.priority|upper }}**: {{ rec.action }}
{% if rec.reason %}_Reason_: {{ rec.reason }}{% endif %}
{% endfor %}
{% else %}
_No specific recommendations generated._
{% endif %}

### Pending Work

{% if pending_items %}
{% for item in pending_items %}

- [ ] {{ item }}
  {% endfor %}
  {% else %}
  _No pending items identified._
  {% endif %}

______________________________________________________________________

## Context for Next Session

### Current State

{{ current_state if current_state else "_No state information captured._" }}

### Open Questions

{% if open_questions %}
{% for question in open_questions %}

- {{ question }}
  {% endfor %}
  {% else %}
  _No open questions identified._
  {% endif %}

### Technical Debt

{% if technical_debt %}
{% for debt_item in technical_debt %}

- **{{ debt_item.severity|upper }}**: {{ debt_item.description }}
  {% if debt_item.location %}_Location_: `{{ debt_item.location }}`{% endif %}
  {% endfor %}
  {% else %}
  _No technical debt explicitly tracked._
  {% endif %}

______________________________________________________________________

## Session Artifacts

### Generated Files

{% if artifacts %}
{% for artifact in artifacts %}

- `{{ artifact.path }}`{% if artifact.description %} - {{ artifact.description }}{% endif %}
  {% endfor %}
  {% else %}
  _No artifacts generated._
  {% endif %}

### Logs & Data

- Session log: `{{ log_path if log_path else "~/.claude/logs/session-buddy.log" }}`
- Reflection database: `{{ db_path if db_path else "~/.claude/data/reflections.db" }}`
  {% if session_data_path %}
- Session data: `{{ session_data_path }}`
  {% endif %}

______________________________________________________________________

## Quality Trends

{% if quality_history %}
**Recent Quality Scores**:
{% for entry in quality_history[-10:] %}

- {{ entry.timestamp|datetime("%Y-%m-%d %H:%M") }}: {{ entry.score }}/100
  {% endfor %}
  {% else %}
  _No quality history available._
  {% endif %}

______________________________________________________________________

## Notes

{% if notes %}
{{ notes }}
{% else %}
_No additional notes for this session._
{% endif %}

______________________________________________________________________

_Generated by session-buddy {{ version }} on {{ session_end|datetime("%Y-%m-%d at %H:%M:%S") }}_
_This handoff document was automatically created to facilitate session continuity._
