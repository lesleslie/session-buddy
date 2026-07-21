______________________________________________________________________

## status: active role: canonical date: 2026-07-16 last_reviewed: 2026-07-16 superseded_by: null blocks_on: [] topic: plugin-standardization

# Checkpoint {{ checkpoint_number }} - {{ project_name }}

**Session ID**: `{{ session_id }}`
**Checkpoint Time**: {{ checkpoint_time|datetime("%Y-%m-%d %H:%M:%S") }}
**Quality Score**: {{ quality_score }}/100 ({{ quality_delta|abs }} {{ "↑" if quality_delta > 0 else "↓" if quality_delta < 0 else "→" }})

______________________________________________________________________

## Summary

{{ summary }}

______________________________________________________________________

## Recent Activity

{% if recent_changes %}

### Changes Since Last Checkpoint

{% for change in recent_changes %}

- {{ change }}
  {% endfor %}
  {% else %}
  _No significant changes tracked._
  {% endif %}

### Files Modified

{% if modified_files %}
{% for file in modified_files[:10] %}

- `{{ file }}`
  {% endfor %}
  {% if modified_files|length > 10 %}
  _...and {{ modified_files|length - 10 }} more files_
  {% endif %}
  {% else %}
  _No files modified._
  {% endif %}

______________________________________________________________________

## Quality Factors

{% if quality_factors %}
{% for factor, score in quality_factors.items() %}

- **{{ factor }}**: {{ score }}/100
  {% endfor %}
  {% else %}
  _Quality factors not available._
  {% endif %}

______________________________________________________________________

## Recommendations

{% if recommendations %}
{% for rec in recommendations[:5] %}
{{ loop.index }}. {{ rec }}
{% endfor %}
{% else %}
_No specific recommendations at this time._
{% endif %}

______________________________________________________________________

_Checkpoint created by session-buddy {{ version }}_
