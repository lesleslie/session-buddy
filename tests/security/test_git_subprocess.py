"""Git subprocess security tests.

Tests for git operation security, including prune delay validation.
"""

import pytest
from session_buddy.utils.git_worktrees import _validate_prune_delay


def test_prune_delay_valid_values():
    """Test valid prune delay values are accepted."""

    # Should accept valid formats
    valid, msg = _validate_prune_delay("2.weeks")
    assert valid is True
    assert msg == ""

    valid, msg = _validate_prune_delay("now")
    assert valid is True
    assert msg == ""

    valid, msg = _validate_prune_delay("never")
    assert valid is True
    assert msg == ""

    valid, msg = _validate_prune_delay("10.days")
    assert valid is True
    assert msg == ""

    valid, msg = _validate_prune_delay("1.hour")
    assert valid is True
    assert msg == ""

    # Test case insensitive
    valid, msg = _validate_prune_delay("5.WEEKS")
    assert valid is True
    assert msg == ""


def test_prune_delay_excessive_blocked():
    """Test excessive values are blocked."""

    # Should block values > 1000
    valid, msg = _validate_prune_delay("10000.weeks")
    assert valid is False
    assert "too large" in msg.lower()
    assert "10000" in msg
    assert "1000" in msg

    valid, msg = _validate_prune_delay("9999.days")
    assert valid is False
    assert "too large" in msg.lower()

    # Test boundary
    valid, msg = _validate_prune_delay("1001.weeks")
    assert valid is False
    assert "too large" in msg.lower()


def test_prune_delay_minimum_blocked():
    """Test values below minimum are blocked."""

    # Should block values < 1
    valid, msg = _validate_prune_delay("0.weeks")
    assert valid is False
    assert "too small" in msg.lower()
    assert "0" in msg

    valid, msg = _validate_prune_delay("-5.days")
    assert valid is False
    assert "Invalid" in msg


def test_prune_delay_invalid_format():
    """Test invalid formats are blocked."""

    # Should block invalid formats
    valid, msg = _validate_prune_delay("malicious")
    assert valid is False
    assert "Invalid prune delay" in msg

    valid, msg = _validate_prune_delay("$(reboot)")
    assert valid is False
    assert "Invalid prune delay" in msg

    valid, msg = _validate_prune_delay("; rm -rf /")
    assert valid is False
    assert "Invalid prune delay" in msg

    valid, msg = _validate_prune_delay("2weeks")  # Missing dot
    assert valid is False
    assert "Invalid prune delay" in msg


def test_prune_delay_upper_boundary():
    """Test upper boundary is accepted."""

    # Should accept exactly 1000
    valid, msg = _validate_prune_delay("1000.weeks")
    assert valid is True
    assert msg == ""

    valid, msg = _validate_prune_delay("1000.years")
    assert valid is True
    assert msg == ""


def test_prune_delay_lower_boundary():
    """Test lower boundary is accepted."""

    # Should accept exactly 1
    valid, msg = _validate_prune_delay("1.second")
    assert valid is True
    assert msg == ""

    valid, msg = _validate_prune_delay("1.week")
    assert valid is True
    assert msg == ""


def test_prune_delay_reasonable_values():
    """Test reasonable values are all accepted."""

    # Test common reasonable values
    reasonable_values = [
        "1.week",
        "2.weeks",
        "14.days",
        "30.days",
        "6.months",
        "1.year",
        "100.weeks",  # ~2 years
        "500.days",   # ~1.4 years
    ]

    for value in reasonable_values:
        valid, msg = _validate_prune_delay(value)
        assert valid is True, f"Should accept {value}: {msg}"
        assert msg == ""
