"""Release consistency suite with release-local version selection."""
from __future__ import annotations
import importlib.util
from pathlib import Path

_PATH = Path(__file__).with_name("release_consistency_core.py")
_SPEC = importlib.util.spec_from_file_location("release_consistency_core", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_CORE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_CORE)
_CORE.VERSION = "0.2.0-alpha.33"
ReleaseConsistencyTests = _CORE.ReleaseConsistencyTests
