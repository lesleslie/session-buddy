"""Shared wire-shape helpers for FastMCP regression tests.

Per the bodai-search-infrastructure-fix plan §5 (REQ-012), regression
tests assert on the wire-shape envelope of a tool call (the JSON
``result.content[0].text`` payload) rather than on the in-process
return value of the handler. The helpers in this package keep the
wire-shape parsing logic in one place so per-tool test files don't
reimplement it.
"""