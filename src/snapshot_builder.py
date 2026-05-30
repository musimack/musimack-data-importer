"""Compatibility wrapper for GA4 snapshot building."""

from __future__ import annotations

import sys

from .providers.ga4 import snapshot_builder as _snapshot_builder

sys.modules[__name__] = _snapshot_builder
