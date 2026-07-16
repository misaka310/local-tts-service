from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..errors import ProviderError
from ..models import ModelConfig, WorkflowTargetConfig
from .base import BaseRuntime, SynthesizeRequest, SynthesizeResult

_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}


@dataclass(frozen=True)
class _PatchTarget:
    node_id: str
    input_key: str


class ComfyUIRuntime(BaseRuntime):
    name = "comfyui"

    def __init__(
        self,
        output_dir: Path,
        models: dict[str, ModelConfig],
        base_url: str,
        input_dir: Path,
        comfy_output_dir: Path,
        timeout_sec: int = 300,
        poll_interval_sec: float = 1.0,
        default_audio_ext: str = ".wav",
        auto_launch: bool = False,
        launch_bat_path: Path | None = None,
        launch_working_dir: Path | None = None,
        startup_timeout_sec: int = 120,
        startup_poll_interval_sec: float = 1.0,
        health_path: str = "/system_stats",
        runtime_log_dir: Path | None = None,
    ) -> None:
        self.output_dir = output_dir
        self.models = models
        self.base_url = base_url.rstrip("/")
        self.input_dir = input_dir
        self.comfy_output_dir = comfy_output_dir
        self.timeout_sec = int(timeout_sec)
        self.poll_interval_sec = float(poll_interval_sec)
        self.default_audio_ext = default_audio_ext if str(default_audio_ext).startswith(".") else f".{default_audio_ext}"
        self.auto_launch = bool(auto_launch)
        self.launch_bat_path = launch_bat_path.resolve() if launch_bat_path is not None else None
        self.launch_working_dir = launch_working_dir.resolve() if launch_working_dir is not None else None
        self.startup_timeout_sec = int(startup_timeout_sec)
        self.startup_poll_interval_sec = float(startup_poll_interval_sec)
        self.health_path = str(health_path or "/system_stats").strip() or "/system_stats"
        self.runtime_log_dir = runtime_log_dir.resolve() if runtime_log_dir is not None else (self.output_dir.parent / "logs").resolve()

    def synthesize(self, request: SynthesizeRequest) -> SynthesizeResult:
        model_cfg = self.models.get(request.model_name)
        if model_cfg is None:
            raise ProviderError(f"model is not configured: {request.model_name}")
        if model_cfg.workflow_path is None:
            raise ProviderError(f"workflowPath is required for model: {request.model_name}")

        self._ensure_server_ready()

        workflow_path = model_cfg.workflow_path
        if not workflow_path.is_file():
            raise ProviderError(f"workflowPath not found: {workflow_path}")
        if not self.input_dir.is_dir():
            raise ProviderError(f"comfyui inputDir not found: {self.input_dir}")
        if not self.comfy_output_dir.is_dir():
            raise ProviderError(f"comfyui outputDir not found: {self.comfy_output_dir}")

        raw_workflow = self._load_json(workflow_path)
        prompt = self._as_prompt(raw_workflow)
        prompt = self._replace_tokens(copy.deepcopy(prompt), request.output_basename)

        text_target = self._resolve_target(
            prompt=prompt,
            target_name="text",
            explicit_target=model_cfg.workflow_targets.text if model_cfg.workflow_targets else None,
            class_hints=("Qwen3VoiceClone", "Irodori", "Text", "Prompt", "TTS"),
            keys=("text", "prompt", "sentence"),
            required=True,
            missing_message="text patch target was not found in workflow",
        )
        effective_text = request.text
        effective_caption = self._normalize_caption(request.caption) or self._normalize_caption(model_cfg.default_caption)
        supports_caption = bool(model_cfg.supports_caption)
        if supports_caption and effective_caption:
            caption_target = self._resolve_target(
                prompt=prompt,
                target_name="caption",
                explicit_target=model_cfg.workflow_targets.caption if model_cfg.workflow_targets else None,
                class_hints=("Irodori", "Qwen3VoiceClone", "Text", "Prompt", "TTS"),
                keys=("caption", "voice_caption", "style", "prompt", "description"),
                required=False,
                missing_message="caption patch target was not found in workflow",
            )
            if caption_target is None or caption_target == text_target:
                effective_text = self._merge_caption_and_text(effective_caption, request.text)
            else:
                self._set_input(prompt, caption_target, effective_caption)
        self._set_input(prompt, text_target, effective_text)
        if request.seed is not None and model_cfg.workflow_targets and model_cfg.workflow_targets.seed is not None:
            seed_target = self._resolve_target(
                prompt=prompt,
                target_name="seed",
                explicit_target=model_cfg.workflow_targets.seed,
                class_hints=("Irodori", "Sampler", "TTS"),
                keys=("seed",),
                required=True,
                missing_message="seed patch target was not found in workflow",
            )
            if seed_target is not None:
                self._set_input(prompt, seed_target, int(request.seed))

        save_target = self._resolve_target(
            prompt=prompt,
            target_name="saveAudio",
            explicit_target=model_cfg.workflow_targets.save_audio if model_cfg.workflow_targets else None,
            class_hints=("SaveAudio", "VHS_SaveAudio"),
            keys=("filename_prefix", "filename", "output_name", "basename"),
            required=True,
            missing_message="save-audio patch target was not found in workflow",
        )
        self._set_input(prompt, save_target, request.output_basename)

        requires_ref = bool(model_cfg.requires_reference_audio)
        reference_audio_path = request.reference_audio_path
        reference_text_path = request.reference_text_path

        if requires_ref:
            if reference_audio_path is None:
                raise ProviderError(f"referenceAudioPath is required for model: {request.model_name}")

        if reference_audio_path is not None:
            if not reference_audio_path.is_file():
                raise ProviderError(f"referenceAudioPath not found: {reference_audio_path}")
            ref_name = self._copy_reference_audio(reference_audio_path)
            ref_target = self._resolve_target(
                prompt=prompt,
                target_name="referenceAudio",
                explicit_target=model_cfg.workflow_targets.reference_audio if model_cfg.workflow_targets else None,
                class_hints=("Qwen3VoiceClone", "Irodori", "ReferenceAudio", "LoadAudio", "Audio"),
                keys=("ref_audio", "audio", "filename", "file", "path"),
                required=requires_ref,
                missing_message="reference-audio patch target was not found in workflow",
            )
            if ref_target is not None:
                self._set_input(prompt, ref_target, ref_name)
        if reference_text_path is not None:
            if not reference_text_path.is_file():
                raise ProviderError(f"referenceTextPath not found: {reference_text_path}")
            reference_text = reference_text_path.read_text(encoding="utf-8-sig").strip()
            ref_text_target = self._resolve_target(
                prompt=prompt,
                target_name="referenceText",
                explicit_target=model_cfg.workflow_targets.reference_text if model_cfg.workflow_targets else None,
                class_hints=("Qwen3VoiceClone", "Irodori", "ReferenceText", "VoiceClone", "Qwen3"),
                keys=("ref_text", "reference_text", "referenceText", "prompt_ref", "audio_prompt_text", "prompt"),
                required=False,
                missing_message="reference-text patch target was not found in workflow",
            )
            if ref_text_target is not None and reference_text:
                self._set_input(prompt, ref_text_target, reference_text)

        before_snapshot = {p.as_posix() for p in self._list_audio_files(self.comfy_output_dir)}
        started_at = datetime.now(timezone.utc).timestamp()

        submitted = self._http_json("POST", f"{self.base_url}/prompt", {"prompt": prompt, "client_id": str(uuid.uuid4())})
        prompt_id = str(submitted.get("prompt_id") or "").strip()
        if not prompt_id:
            raise ProviderError("ComfyUI /prompt did not return prompt_id")

        history_entry = self._wait_history(prompt_id)
        generated = self._extract_generated_files(history_entry)

        source: Path | None = None
        if generated:
            for item in generated:
                candidate = (self.comfy_output_dir / item.get("subfolder", "") / item["filename"]).resolve()
                if candidate.is_file():
                    source = candidate
                    break

        if source is None:
            after_files = self._list_audio_files(self.comfy_output_dir)
            prefix_matches = [p for p in after_files if request.output_basename in p.name]
            new_files = [p for p in after_files if p.as_posix() not in before_snapshot]
            recent_files = [p for p in after_files if p.stat().st_mtime >= started_at - 2.0]
            pool = prefix_matches or new_files or recent_files or after_files
            if not pool:
                raise ProviderError("ComfyUI did not create an audio file")
            source = max(pool, key=lambda p: p.stat().st_mtime)

        requested_ext = ".wav" if str(request.output_format).lower() == "wav" else (source.suffix or self.default_audio_ext)
        suffix = requested_ext or source.suffix or self.default_audio_ext
        out_file = self.output_dir / f"{request.output_basename}{suffix}"
        out_file.parent.mkdir(parents=True, exist_ok=True)
        if suffix.lower() == ".wav" and source.suffix.lower() != ".wav":
            self._convert_to_wav(source, out_file)
        else:
            shutil.copy2(source, out_file)

        return SynthesizeResult(runtime=self.name, model=request.model_name, audio_path=out_file)

    def _load_json(self, path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise ProviderError(f"failed to read JSON: {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ProviderError(f"workflow JSON must be object: {path}")
        return payload

    def _as_prompt(self, workflow: dict[str, Any]) -> dict[str, Any]:
        if self._is_prompt_format(workflow):
            return workflow

        nodes = workflow.get("nodes")
        if not isinstance(nodes, list):
            raise ProviderError("workflow JSON must be API prompt object or include nodes[]")

        links = workflow.get("links")
        link_by_id: dict[str, tuple[str, int]] = {}
        if isinstance(links, list):
            for item in links:
                if isinstance(item, list) and len(item) >= 4:
                    link_id = str(item[0])
                    from_node = str(item[1])
                    from_slot = int(item[2])
                    link_by_id[link_id] = (from_node, from_slot)

        prompt: dict[str, Any] = {}
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", "")).strip()
            class_type = str(node.get("class_type") or node.get("type") or "").strip()
            if not node_id or not class_type:
                continue

            inputs: dict[str, Any] = {}
            inputs_meta = node.get("inputs")
            if isinstance(inputs_meta, list):
                widgets = node.get("widgets_values") if isinstance(node.get("widgets_values"), list) else []
                widget_index = 0
                widget_inputs: list[tuple[str, str]] = []

                def value_matches_input_type(expected_type: str, candidate: Any) -> bool:
                    kind = expected_type.upper()
                    if kind == "BOOLEAN":
                        return isinstance(candidate, bool)
                    if kind in ("INT", "INTEGER"):
                        return isinstance(candidate, int) and not isinstance(candidate, bool)
                    if kind in ("FLOAT", "NUMBER"):
                        return isinstance(candidate, (int, float)) and not isinstance(candidate, bool)
                    if kind in ("STRING", "COMBO"):
                        return isinstance(candidate, str)
                    return True

                for item in inputs_meta:
                    if not isinstance(item, dict):
                        continue
                    key = str(item.get("name") or "").strip()
                    if not key:
                        continue

                    link_ref = item.get("link")
                    if link_ref is not None:
                        mapped = link_by_id.get(str(link_ref))
                        if mapped:
                            inputs[key] = [mapped[0], mapped[1]]
                        continue

                    if "widget" in item:
                        input_type = str(item.get("type") or "")
                        widget_inputs.append((key, input_type))
                        continue

                    if "default" in item:
                        inputs[key] = copy.deepcopy(item["default"])

                for widget_name, widget_type in widget_inputs:
                    while widget_index < len(widgets):
                        candidate = widgets[widget_index]
                        widget_index += 1
                        if value_matches_input_type(widget_type, candidate):
                            inputs[widget_name] = copy.deepcopy(candidate)
                            break

            prompt[node_id] = {"class_type": class_type, "inputs": inputs}

        if not prompt:
            raise ProviderError("no valid nodes in workflow")
        return prompt

    def _is_prompt_format(self, value: dict[str, Any]) -> bool:
        if not value:
            return False
        for node in value.values():
            if not isinstance(node, dict):
                return False
            if "class_type" not in node and "type" not in node:
                return False
        return True

    def _replace_tokens(self, value: Any, basename: str) -> Any:
        if isinstance(value, str):
            return value.replace("{{OUTPUT_BASENAME}}", basename)
        if isinstance(value, list):
            return [self._replace_tokens(item, basename) for item in value]
        if isinstance(value, dict):
            return {k: self._replace_tokens(v, basename) for k, v in value.items()}
        return value

    def _find_target(self, prompt: dict[str, Any], class_hints: tuple[str, ...], keys: tuple[str, ...]) -> _PatchTarget | None:
        for node_id, node in prompt.items():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type") or node.get("type") or "")
            if class_hints and not any(hint.lower() in class_type.lower() for hint in class_hints):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for key in keys:
                if key in inputs:
                    return _PatchTarget(node_id=node_id, input_key=key)
        return None

    def _resolve_target(
        self,
        prompt: dict[str, Any],
        target_name: str,
        explicit_target: WorkflowTargetConfig | None,
        class_hints: tuple[str, ...],
        keys: tuple[str, ...],
        required: bool,
        missing_message: str,
    ) -> _PatchTarget | None:
        if explicit_target is not None:
            node = prompt.get(explicit_target.node_id)
            if not isinstance(node, dict):
                raise ProviderError(
                    f"workflowTargets.{target_name} is invalid: nodeId '{explicit_target.node_id}' was not found"
                )
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                raise ProviderError(
                    f"workflowTargets.{target_name} is invalid: nodeId '{explicit_target.node_id}' has no inputs object"
                )
            if explicit_target.input_key not in inputs:
                raise ProviderError(
                    f"workflowTargets.{target_name} is invalid: inputKey '{explicit_target.input_key}' was not found in nodeId '{explicit_target.node_id}'"
                )
            return _PatchTarget(node_id=explicit_target.node_id, input_key=explicit_target.input_key)

        found = self._find_target(prompt, class_hints=class_hints, keys=keys)
        if found is None and required:
            raise ProviderError(missing_message)
        return found

    def _set_input(self, prompt: dict[str, Any], target: _PatchTarget, value: Any) -> None:
        node = prompt.get(target.node_id)
        if not isinstance(node, dict):
            raise ProviderError("invalid workflow node")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            raise ProviderError("invalid workflow node inputs")
        inputs[target.input_key] = value

    def _normalize_caption(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
        return normalized or None

    def _merge_caption_and_text(self, caption: str, text: str) -> str:
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return caption
        return f"{caption}\n\n{normalized_text}"

    def _copy_reference_audio(self, source_path: Path) -> str:
        suffix = source_path.suffix or ".wav"
        filename = f"tts-ref-{uuid.uuid4().hex[:12]}{suffix}"
        target = (self.input_dir / filename).resolve()
        shutil.copy2(source_path, target)
        return filename

    def _http_json(self, method: str, url: str, payload: dict[str, Any] | None = None, timeout: int = 30) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ProviderError(f"HTTP {exc.code} from {url}: {detail}") from exc
        except URLError as exc:
            raise ProviderError(f"cannot connect to {url}: {exc.reason}") from exc

        try:
            parsed = json.loads(body or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderError(f"invalid JSON response from {url}") from exc

        if not isinstance(parsed, dict):
            raise ProviderError(f"unexpected JSON response from {url}")
        return parsed

    def _wait_history(self, prompt_id: str) -> dict[str, Any]:
        deadline = time.time() + self.timeout_sec
        while time.time() < deadline:
            payload = self._http_json("GET", f"{self.base_url}/history/{prompt_id}", timeout=30)
            entry = payload.get(prompt_id)
            if isinstance(entry, dict):
                error_message = self._history_error(entry)
                if error_message:
                    raise ProviderError(f"ComfyUI history error: {error_message}")
                return entry
            time.sleep(max(0.2, self.poll_interval_sec))
        raise ProviderError(f"timeout waiting for ComfyUI prompt_id={prompt_id}")

    def _history_error(self, entry: dict[str, Any]) -> str | None:
        status = entry.get("status")
        if not isinstance(status, dict):
            return None
        status_text = str(status.get("status_str") or status.get("status") or "").lower()
        if status_text != "error":
            return None
        messages = status.get("messages")
        if not isinstance(messages, list):
            return "status=error; messages unavailable"
        snippets: list[str] = []
        for message in messages:
            if isinstance(message, list) and len(message) >= 2 and isinstance(message[1], dict):
                payload = message[1]
                node_id = payload.get("node_id")
                node_type = payload.get("node_type")
                exc_message = payload.get("exception_message") or payload.get("exception_type") or payload
                snippets.append(f"node_id={node_id} node_type={node_type} error={exc_message}")
        return " | ".join(snippets) or "status=error"

    def _extract_generated_files(self, history_entry: dict[str, Any]) -> list[dict[str, str]]:
        outputs = history_entry.get("outputs")
        if not isinstance(outputs, dict):
            return []

        found: list[dict[str, str]] = []
        for node in outputs.values():
            if not isinstance(node, dict):
                continue
            for key in ("audio", "files"):
                payload = node.get(key)
                if not isinstance(payload, list):
                    continue
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    filename = item.get("filename")
                    if not filename:
                        continue
                    found.append(
                        {
                            "filename": str(filename),
                            "subfolder": str(item.get("subfolder", "")),
                        }
                    )
        return found

    def _list_audio_files(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        return [path.resolve() for path in root.rglob("*") if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS]

    def _convert_to_wav(self, source: Path, destination: Path) -> None:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-acodec",
            "pcm_s16le",
            str(destination),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError as exc:
            raise ProviderError("ffmpeg command was not found; cannot convert audio to wav") from exc

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise ProviderError(f"ffmpeg conversion failed: {detail}")

    def _ensure_server_ready(self) -> None:
        if self._is_server_healthy():
            return
        if not self.auto_launch:
            raise ProviderError(
                f"ComfyUI is not reachable at {self.base_url} "
                f"(health={self._health_url()}). Set runtimes.comfyui.autoLaunch=true to start it automatically."
            )
        self._launch_comfyui()
        deadline = time.time() + max(1, self.startup_timeout_sec)
        while time.time() < deadline:
            if self._is_server_healthy():
                return
            time.sleep(max(0.2, self.startup_poll_interval_sec))
        launch_target = str(self.launch_bat_path) if self.launch_bat_path is not None else "(unset)"
        raise ProviderError(
            "ComfyUI auto-launch timed out. "
            f"launchBatPath={launch_target}, "
            f"baseUrl={self.base_url}, "
            f"healthUrl={self._health_url()}, "
            f"logs={self._stdout_log_path()} / {self._stderr_log_path()}"
        )

    def _health_url(self) -> str:
        if self.health_path.startswith("http://") or self.health_path.startswith("https://"):
            return self.health_path
        normalized = self.health_path if self.health_path.startswith("/") else f"/{self.health_path}"
        return f"{self.base_url}{normalized}"

    def _is_server_healthy(self) -> bool:
        for url in (self._health_url(), self.base_url):
            try:
                req = Request(url, method="GET")
                with urlopen(req, timeout=2) as response:
                    status = getattr(response, "status", 200)
                    if 200 <= int(status) < 500:
                        return True
            except (HTTPError, URLError, ValueError, OSError, TimeoutError):
                continue
        return False

    def check_health(self) -> bool:
        """Public health interface used by service diagnostics."""
        return self._is_server_healthy()

    def _launch_comfyui(self) -> None:
        if self.launch_bat_path is None:
            raise ProviderError(
                "ComfyUI auto-launch is enabled but launchBatPath is not configured. "
                f"Expected a .bat file for {self.base_url}."
            )
        if not self.launch_bat_path.is_file():
            raise ProviderError(f"ComfyUI launchBatPath not found: {self.launch_bat_path}")
        if self.launch_working_dir is None:
            raise ProviderError(
                "ComfyUI auto-launch is enabled but launchWorkingDir is not configured. "
                f"launchBatPath={self.launch_bat_path}"
            )
        if not self.launch_working_dir.is_dir():
            raise ProviderError(f"ComfyUI launchWorkingDir not found: {self.launch_working_dir}")

        self.runtime_log_dir.mkdir(parents=True, exist_ok=True)
        with self._stdout_log_path().open("ab") as stdout_fp, self._stderr_log_path().open("ab") as stderr_fp:
            env = dict(os.environ)
            env["VOICE_STACK_CONTROLLED"] = "1"
            try:
                subprocess.Popen(
                    ["cmd.exe", "/c", str(self.launch_bat_path)],
                    cwd=str(self.launch_working_dir),
                    env=env,
                    stdout=stdout_fp,
                    stderr=stderr_fp,
                )
            except OSError as exc:
                raise ProviderError(
                    "ComfyUI auto-launch failed to start process. "
                    f"launchBatPath={self.launch_bat_path}, "
                    f"launchWorkingDir={self.launch_working_dir}, "
                    f"logs={self._stdout_log_path()} / {self._stderr_log_path()}"
                ) from exc

    def _stdout_log_path(self) -> Path:
        return self.runtime_log_dir / "comfyui-runtime.out.log"

    def _stderr_log_path(self) -> Path:
        return self.runtime_log_dir / "comfyui-runtime.err.log"
