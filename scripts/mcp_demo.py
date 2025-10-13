"""MCP demo module (safe to delete).

This file is only for testing symbol-level edit tools.
"""


def hello() -> str:
    return "v2"


def added_after() -> str:
    return "after"


def added_before() -> str:
    return "before"


class Demo:
    def ping(self) -> str:
        return "pong"
