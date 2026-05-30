"""Compatibility wrapper for the GA4 provider client module."""

from __future__ import annotations

import sys

from .providers.ga4 import client as _client

sys.modules[__name__] = _client
