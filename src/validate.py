"""Compatibility wrapper for GA4 snapshot validation."""

from __future__ import annotations

import sys

from .providers.ga4 import validate as _validate

sys.modules[__name__] = _validate
