import os
from contextlib import contextmanager
from typing import Dict, Iterator, MutableMapping, Optional

ACTIVE_ENV = "AI_DEV_TOOL_ACTIVE"
CALLER_ENV = "AI_DEV_TOOL_ACTIVE_BY"


def is_active(env: Optional[MutableMapping[str, str]] = None) -> bool:
    env = env if env is not None else os.environ
    return env.get(ACTIVE_ENV) == "1"


def activated_env(
    base_env: Optional[MutableMapping[str, str]] = None,
    *,
    caller: str = "lib",
) -> Dict[str, str]:
    env = dict(base_env if base_env is not None else os.environ)
    env[ACTIVE_ENV] = "1"
    env[CALLER_ENV] = caller
    return env


@contextmanager
def activated(*, caller: str = "lib") -> Iterator[None]:
    old_active = os.environ.get(ACTIVE_ENV)
    old_caller = os.environ.get(CALLER_ENV)
    os.environ[ACTIVE_ENV] = "1"
    os.environ[CALLER_ENV] = caller
    try:
        yield
    finally:
        if old_active is None:
            os.environ.pop(ACTIVE_ENV, None)
        else:
            os.environ[ACTIVE_ENV] = old_active
        if old_caller is None:
            os.environ.pop(CALLER_ENV, None)
        else:
            os.environ[CALLER_ENV] = old_caller
