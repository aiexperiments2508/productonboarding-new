"""The external system estate.

    manifest   who the systems are, what they emit, how well they behave
    defects    the closed set of ways a payload can be wrong
    emitter    a system's profile turned into a seeded batch schedule
    server     one MCP server per system

Nothing outside this package names a system. That is the property that makes
the estate pluggable rather than merely plural, and `tests/test_estate.py`
asserts it.
"""
