from __future__ import annotations

import codecs
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_start_local_tts_stack_uses_utf8_bom_for_windows_powershell_51() -> None:
    data = (ROOT / "scripts" / "start-local-tts-stack.ps1").read_bytes()

    assert data.startswith(codecs.BOM_UTF8)

def test_start_tts_frontend_skips_rvc_preflight_on_worker_role() -> None:
    source = (ROOT / "scripts" / "start-tts-frontend.ps1").read_text(encoding="utf-8-sig")

    assert "if ($deployment.Role -in @('frontend', 'worker')) {" in source
    assert "    $rvcRoot = ''" in source


def test_f5_setup_uses_the_managed_python_runtime() -> None:
    source = (ROOT / "scripts" / "setup-f5-tts.ps1").read_text(encoding="utf-8-sig")

    assert "python-runtime.ps1" in source
    assert "Install-LocalTtsManagedPythonRuntime" in source
    assert "Get-Command python" not in source
