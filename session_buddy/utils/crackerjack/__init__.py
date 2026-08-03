"""Crackerjack integration utilities.

This package provides modular utilities for Crackerjack tool integration including:
- Pattern building for output parsing
- Output parsing and insight extraction
- Database operations for result storage

All modules are designed to be reusable and testable components that reduce
code duplication in the main crackerjack_integration module.
"""

from session_buddy.utils.crackerjack.output_parser import CrackerjackOutputParser
from session_buddy.utils.crackerjack.pattern_builder import PatternMappingsBuilder
from session_buddy.utils.crackerjack.fallback import try_crackerjack_cli

__all__ = [
    "CrackerjackOutputParser",
    "PatternMappingsBuilder",
    "try_crackerjack_cli",
]
