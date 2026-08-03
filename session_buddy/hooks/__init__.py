"""Session-Buddy hooks package.

Cross-cutting utilities for hook event handling. The package is additive
— production imports remain unchanged.
"""

from __future__ import annotations

from .single_flight import HookSingleFlight

__all__ = ["HookSingleFlight"]
