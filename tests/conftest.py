import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(autouse=True)
def _isolate_kimi_cli_credentials(tmp_path_factory, monkeypatch):
    """Never let the suite read the developer's real ~/.kimi-code credentials."""
    from kimi_code_usage.providers import kimi_membership

    path = tmp_path_factory.mktemp("kimi-cred") / "kimi-code.json"
    monkeypatch.setattr(kimi_membership, "_KIMI_CLI_CREDENTIALS_PATH", str(path))
