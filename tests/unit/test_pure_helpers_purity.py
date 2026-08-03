import inspect

from session_buddy.crackerjack_integration import CrackerjackIntegration


HELPER_NAMES = [
    "_calculate_lint_metrics",
    "_calculate_security_metrics",
    "_calculate_complexity_metrics",
    "_calculate_coverage_metrics",
]


def test_helpers_are_staticmethod_on_class():
    """After refactor, the four pure helpers must be @staticmethod on CrackerjackIntegration."""
    for name in HELPER_NAMES:
        attr = inspect.getattr_static(CrackerjackIntegration, name)
        assert isinstance(attr, staticmethod), (
            f"{name} must be a @staticmethod on CrackerjackIntegration; got {type(attr).__name__}"
        )


def test_helpers_callable_via_class_without_instance():
    """Helper invocation must work via CrackerjackIntegration._calculate_X(args) without instantiating."""
    assert isinstance(CrackerjackIntegration._calculate_lint_metrics([]), dict)
    assert isinstance(CrackerjackIntegration._calculate_security_metrics([]), dict)
    assert isinstance(CrackerjackIntegration._calculate_complexity_metrics({}), dict)
    assert isinstance(CrackerjackIntegration._calculate_coverage_metrics({}), dict)


def test_helpers_have_no_self_access():
    """Static body check: each helper's source must not access self (other than the def line)."""
    import inspect
    for name in HELPER_NAMES:
        source = inspect.getsource(getattr(CrackerjackIntegration, name))
        # Crude but effective: no "self." accesses anywhere in the body
        assert "self." not in source, f"{name} accesses self: {source}"