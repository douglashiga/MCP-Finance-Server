import pytest
from fastapi import HTTPException

import dataloader.app as app_module


def test_validate_script_filename_accepts_top_level_py():
    assert app_module._validate_script_filename("job_runner.py") == "job_runner.py"


@pytest.mark.parametrize("filename", ["../evil.py", "nested/evil.py", "evil.sh", ".hidden.py", ""])
def test_validate_script_filename_rejects_invalid_names(filename):
    with pytest.raises(HTTPException):
        app_module._validate_script_filename(filename)


def test_resolve_script_path_stays_inside_scripts_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "SCRIPTS_DIR_PATH", tmp_path.resolve())
    resolved = app_module._resolve_script_path("safe_job.py")
    assert resolved == (tmp_path / "safe_job.py").resolve()


def test_require_admin_api_key_rejects_when_missing_key(monkeypatch):
    monkeypatch.setattr(app_module, "ALLOW_INSECURE", False)
    monkeypatch.setattr(app_module, "API_KEY", None)
    with pytest.raises(HTTPException) as exc:
        app_module.require_admin_api_key("any")
    assert exc.value.status_code == 503


def test_require_admin_api_key_rejects_invalid_value(monkeypatch):
    monkeypatch.setattr(app_module, "ALLOW_INSECURE", False)
    monkeypatch.setattr(app_module, "API_KEY", "secret")
    with pytest.raises(HTTPException) as exc:
        app_module.require_admin_api_key("wrong")
    assert exc.value.status_code == 401


def test_require_admin_api_key_accepts_valid_value(monkeypatch):
    monkeypatch.setattr(app_module, "ALLOW_INSECURE", False)
    monkeypatch.setattr(app_module, "API_KEY", "secret")
    assert app_module.require_admin_api_key("secret") is None
