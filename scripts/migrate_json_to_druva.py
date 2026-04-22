#!/usr/bin/env python3
"""Compatibility wrapper for the legacy Druva migration module name."""

from __future__ import annotations

from .migrate_json_to_dhruva import (
    JSONInvocation,
    JSONToDhruvaMigrator,
    MigrationStats,
    main,
)

JSONToDruvaMigrator = JSONToDhruvaMigrator

