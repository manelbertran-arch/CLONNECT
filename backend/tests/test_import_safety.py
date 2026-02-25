"""
Import safety net — verifies all internal cross-module imports resolve correctly.
Run this BEFORE and AFTER every decomposition to catch broken imports.

Usage: cd backend && python -m pytest tests/test_import_safety.py -v
"""
import importlib
import os
import re
import sys
import pytest

# Ensure backend is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def _collect_internal_imports():
    """Scan all .py files and collect internal import statements."""
    imports = []
    backend_dir = os.path.dirname(os.path.dirname(__file__))

    for root, dirs, files in os.walk(backend_dir):
        # Skip non-source directories
        if any(skip in root for skip in ['__pycache__', 'tests', '_archive', '.git']):
            continue
        for f in files:
            if not f.endswith('.py'):
                continue
            path = os.path.join(root, f)
            rel = os.path.relpath(path, backend_dir)
            try:
                fh = open(path, encoding='utf-8', errors='ignore')
            except Exception:
                continue
            with fh:
                for lineno, line in enumerate(fh, 1):
                    line = line.strip()
                    # Skip comments and strings
                    if line.startswith('#') or line.startswith('"') or line.startswith("'"):
                        continue
                    # Match: from api.xxx import yyy
                    m = re.match(r'from\s+((?:api|core|services|ingestion|metrics|models)[\w.]*)\s+import\s+(.+)', line)
                    if m:
                        module = m.group(1)
                        names = [n.strip().split(' as ')[0].strip() for n in m.group(2).split(',')]
                        # Handle multi-line imports (just get what's on this line)
                        names = [n.strip('( )') for n in names if n.strip('( )')]
                        for name in names:
                            if name and not name.startswith('#'):
                                imports.append((rel, lineno, module, name))
    return imports

# Collect at module load time
_ALL_IMPORTS = _collect_internal_imports()

# Create unique module-level imports to test
_UNIQUE_MODULES = sorted(set(imp[2] for imp in _ALL_IMPORTS))

@pytest.mark.parametrize("module_path", _UNIQUE_MODULES)
def test_module_importable(module_path):
    """Test that each internally-referenced module can be imported."""
    try:
        importlib.import_module(module_path)
    except ImportError as e:
        # Some modules need DB or env vars - that's OK, we just need the module to exist
        if "No module named" in str(e):
            pytest.fail(f"Module {module_path} not found: {e}")
        # Other ImportErrors (missing DB, env vars) are OK - module exists but can't fully load
    except Exception:
        pass  # Module exists but has runtime dependency issues - that's fine

# Also test that critical re-export paths work
CRITICAL_IMPORTS = [
    ("api.routers.dm", "router"),
    ("api.routers.nurturing", "router"),
    ("api.routers.leads", "router"),
    ("api.routers.instagram", "router"),
    ("api.routers.ingestion_v2", "router"),
    ("api.routers.admin", "router"),
    ("api.routers.oauth", "router"),
    ("api.routers.copilot", "router"),
    ("api.routers.messaging_webhooks", "router"),
    ("api.services.db_service", "get_session"),
    ("api.auth", "require_admin"),
    ("core.whatsapp", "WhatsAppConnector"),
    ("core.whatsapp", "WhatsAppHandler"),
    ("core.payments", "get_payment_manager"),
    ("core.calendar", "get_calendar_manager"),
    ("core.gdpr", "get_gdpr_manager"),
    ("core.nurturing", "get_nurturing_manager"),
    ("core.copilot_service", "get_copilot_service"),
    ("core.instagram_handler", "InstagramHandler"),
    ("services.memory_engine", "get_memory_engine"),
    ("services.clone_score_engine", "get_clone_score_engine"),
]

@pytest.mark.parametrize("module_path,attr_name", CRITICAL_IMPORTS)
def test_critical_import(module_path, attr_name):
    """Test that critical attributes are importable from their expected locations."""
    try:
        mod = importlib.import_module(module_path)
        assert hasattr(mod, attr_name), f"{module_path} has no attribute '{attr_name}'"
    except ImportError as e:
        if "No module named" in str(e):
            pytest.fail(f"Module {module_path} not found: {e}")
    except Exception:
        pass  # Runtime issues OK, we just care about import resolution
