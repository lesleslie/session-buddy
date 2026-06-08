"""Skill Distillation (Phase 1.5 Feature #6).

Background job that watches completed sessions, identifies
successful patterns, and distills them into learnable "skills":
short records of the form "for problems like X, try Y because
Z worked in N prior cases."

The data layer is LLM-optional. The LLM synthesis path is a
Conscious Agent enhancement that rewrites ``suggested_approach``
into better prose — it is NOT a dependency of the data layer.
A regression test (``test_distiller_module_is_llm_optional``) pins
this contract.
"""

from __future__ import annotations

from session_buddy.skills import distiller

__all__ = ["distiller"]
