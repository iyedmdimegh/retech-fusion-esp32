"""Shared pytest fixtures + cross-platform setup."""
from __future__ import annotations

from retech_part2._compat import apply_windows_event_loop_policy

apply_windows_event_loop_policy()
