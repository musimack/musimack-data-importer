"""Compatibility wrapper for GA4 traffic overview normalization."""

from __future__ import annotations

import sys

from .providers.ga4 import normalize as _normalize

sys.modules[__name__] = _normalize
