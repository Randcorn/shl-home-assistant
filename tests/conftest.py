"""Let the HA-free integration modules be tested without Home Assistant.

Importing ``custom_components.shl.<module>`` normally executes the package's
``__init__.py``, which imports Home Assistant. Registering the package with
its real ``__path__`` lets tests import the pure submodules (api, const,
discovery, events, models, polling) without running that ``__init__.py``.
Tests that exercise Home Assistant-facing modules (coordinator, sensor,
config_flow) still need Home Assistant or stubs installed.
"""

import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_shl_pkg = types.ModuleType("custom_components.shl")
_shl_pkg.__path__ = [str(REPO_ROOT / "custom_components" / "shl")]
sys.modules.setdefault("custom_components.shl", _shl_pkg)
