import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
START_SCRIPT = REPO_ROOT / "scripts" / "start-gpt-sovits-api.ps1"
SETUP_SCRIPT = REPO_ROOT / "scripts" / "setup-gpt-sovits.ps1"
STACK_SCRIPT = REPO_ROOT / "scripts" / "start-local-tts-stack.ps1"


def test_gpt_sovits_start_uses_external_python_and_config_without_installing_into_source() -> None:
    script = START_SCRIPT.read_text(encoding="utf-8-sig")

    assert "[string]$ConfigPath" in script
    assert "'-c', $ConfigPath" in script
    assert '-WorkingDirectory $GptSovitsRoot' in script
    assert "setup-gpt-sovits.ps1') -GptSovitsRoot $GptSovitsRoot" in script
    assert "Ensure-GptSovitsEnvironment" not in script
    assert "python -m venv" not in script
    assert "pip install" not in script


def test_gpt_sovits_setup_uses_a_clean_sibling_checkout() -> None:
    script = SETUP_SCRIPT.read_text(encoding="utf-8-sig")

    assert "runtime/vendor/GPT-SoVITS-clean" in script
    assert "runtime/vendor/GPT-SoVITS'" not in script


def test_stack_passes_external_gpt_python_and_config_to_the_managed_api() -> None:
    script = STACK_SCRIPT.read_text(encoding="utf-8-sig")

    assert "-PythonExecutable $gptSovitsPython" in script
    assert "-ConfigPath $gptSovitsConfig" in script


def test_gpt_sovits_gpu_visibility_is_process_scoped_and_configurable() -> None:
    start = START_SCRIPT.read_text(encoding="utf-8-sig")
    stack = STACK_SCRIPT.read_text(encoding="utf-8-sig")
    sample = (REPO_ROOT / "config" / "config.example.json").read_text(encoding="utf-8-sig")

    assert "[string]$VisibleGpuDevices" in start
    assert "$env:CUDA_VISIBLE_DEVICES = $VisibleGpuDevices" in start
    assert "-VisibleGpuDevices $gptSovitsVisibleDevices" in stack
    assert '"gptSovitsVisibleDevices": ""' in sample
def test_gpt_sovits_runtime_paths_follow_the_runtime_junction_target() -> None:
    script = START_SCRIPT.read_text(encoding="utf-8-sig" )

    assert "$RuntimeRoot = Get-LocalTtsRuntimeRoot -RepoRoot $RepoRoot" in script
def test_managed_process_records_follow_the_runtime_junction_target() -> None:
    script = (REPO_ROOT / 'scripts' / 'managed-processes.ps1').read_text(encoding='utf-8-sig')

    assert """$runtimeDirectory.LinkType -eq 'Junction'""" in script
    assert '$runtimeDirectory.Target[0]' in script
def test_gpt_sovits_launch_tracks_python_and_logs_under_runtime_target() -> None:
    script = START_SCRIPT.read_text(encoding='utf-8-sig')

    assert """$LogDir = Join-Path $RuntimeRoot 'logs'""" in script
    assert '-FilePath $PythonExecutable' in script
    assert """LOCAL_TTS_MANAGED_SERVICE = 'gpt-sovits'""" in script
def test_worker_logs_follow_the_runtime_junction_target() -> None:
    script = (REPO_ROOT / 'scripts' / 'start-local-tts.ps1').read_text(encoding='utf-8-sig')

    assert '$logDir = Join-Path (Get-LocalTtsRuntimeRoot -RepoRoot $repoRoot) "logs"' in script

BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "gpt_sovits_api_bootstrap.py"


def _load_bootstrap():
    spec = importlib.util.spec_from_file_location("gpt_sovits_api_bootstrap", BOOTSTRAP_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gpt_sovits_bootstrap_redirects_vendor_cache_and_selects_lite(monkeypatch, tmp_path) -> None:
    bootstrap = _load_bootstrap()
    config = SimpleNamespace(
        cache_dir=Path("vendor/GPT_SoVITS/pretrained_models/fast_langdetect"),
        model="auto",
    )
    instances = []

    class LangDetector:
        def __init__(self, config=None):
            self.config = config
            instances.append(self)

    fast_detect = SimpleNamespace(LangDetector=LangDetector)
    monkeypatch.setattr(bootstrap.importlib, "import_module", lambda _name: fast_detect)
    monkeypatch.setenv("LOCAL_TTS_RUNTIME_ROOT", str(tmp_path))

    cache_dir = bootstrap.configure_language_detector()
    detector = fast_detect.LangDetector(config)

    assert detector.config.model == "lite"
    assert detector.config.cache_dir == str(tmp_path / "gpt-sovits" / "fast-langdetect")
    assert cache_dir.is_dir()
    assert instances == [detector]


def test_gpt_sovits_bootstrap_forwards_api_arguments(monkeypatch, tmp_path) -> None:
    bootstrap = _load_bootstrap()
    api_script = tmp_path / "api_v2.py"
    api_script.write_text("# test entrypoint", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "configure_language_detector", lambda: None)
    captured = {}

    def capture_run_path(path, *, run_name):
        captured.update(path=path, run_name=run_name, argv=list(bootstrap.sys.argv))

    monkeypatch.setattr(bootstrap.runpy, "run_path", capture_run_path)
    bootstrap.main([str(api_script), "-a", "127.0.0.1", "-p", "9880", "-c", "config.yaml"])

    assert captured["path"] == str(api_script.resolve())
    assert captured["run_name"] == "__main__"
    assert captured["argv"] == [str(api_script.resolve()), "-a", "127.0.0.1", "-p", "9880", "-c", "config.yaml"]

def test_gpt_sovits_api_uses_managed_no_window_launcher_for_hidden_start() -> None:
    script = START_SCRIPT.read_text(encoding='utf-8-sig')

    assert "(Join-Path $PSScriptRoot 'no-window-process.ps1')" in script
    assert 'if ($VisibleWindow)' in script
    assert 'Start-LocalTtsNoWindowProcess -FilePath $PythonExecutable' in script
    assert 'Start-Process -FilePath $PythonExecutable -ArgumentList $apiArguments' in script
