from __future__ import annotations

import copy
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..errors import ProviderError
from ..models import ModelConfig
from .base import SynthesizeRequest, SynthesizeResult
from .comfyui import ComfyUIRuntime

_SAVE_AUDIO_CLASSES = {"saveaudio", "vhs_saveaudio"}
_SAVE_AUDIO_KEYS = ("filename_prefix", "filename", "output_name", "basename")


class ComfyUIVoxCPM2Runtime(ComfyUIRuntime):
    name = "comfyui_voxcpm2"

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
    ) -> None:
        super().__init__(
            output_dir=output_dir,
            models=models,
            base_url=base_url,
            input_dir=input_dir,
            comfy_output_dir=comfy_output_dir,
            timeout_sec=timeout_sec,
            poll_interval_sec=poll_interval_sec,
            default_audio_ext=default_audio_ext,
        )

    def synthesize(self, request: SynthesizeRequest) -> SynthesizeResult:
        model_cfg = self.models.get(request.model_name)
        if model_cfg is None:
            raise ProviderError(f"model is not configured: {request.model_name}")
        if model_cfg.workflow_path is None:
            raise ProviderError(f"workflowPath is required for model: {request.model_name}")

        workflow_path = model_cfg.workflow_path
        if not workflow_path.is_file():
            raise ProviderError(f"workflowPath not found: {workflow_path}")
        if not self.input_dir.is_dir():
            raise ProviderError(f"comfyui inputDir not found: {self.input_dir}")
        if not self.comfy_output_dir.is_dir():
            raise ProviderError(f"comfyui outputDir not found: {self.comfy_output_dir}")

        prompt = self._replace_tokens(self._as_prompt(self._load_json(workflow_path)), request.output_basename)
        prompt = copy.deepcopy(prompt)

        tts_node_ids = self._find_node_ids(prompt, "VoxCPM2_TTS")
        clone_node_ids = self._find_node_ids(prompt, "VoxCPM2_Clone")
        if not tts_node_ids and not clone_node_ids:
            raise ProviderError("VoxCPM2 workflow text patch target was not found (VoxCPM2_TTS or VoxCPM2_Clone)")

        save_audio_node_ids = self._find_save_audio_node_ids(prompt)
        if not save_audio_node_ids:
            raise ProviderError(
                "VoxCPM2 workflow must include SaveAudio-compatible node so generated audio can be copied"
            )
        for node_id in save_audio_node_ids:
            self._set_save_audio_basename(prompt, node_id, request.output_basename)

        for node_id in tts_node_ids + clone_node_ids:
            self._set_input_value(prompt, node_id, "text", request.text)

        voice_description = (
            self._normalize_voice_description(request.voice_description)
            or self._normalize_voice_description(request.caption)
            or self._normalize_voice_description(model_cfg.voice_description)
        )
        if voice_description:
            for node_id in tts_node_ids + clone_node_ids:
                self._set_input_value(prompt, node_id, "voice_description", voice_description)

        load_audio_node_ids = self._find_node_ids(prompt, "LoadAudio")
        copied_reference_name: str | None = None

        requires_ref = bool(model_cfg.requires_reference_audio)
        if requires_ref and model_cfg.reference_audio_path is None:
            raise ProviderError(f"referenceAudioPath is required for model: {request.model_name}")
        if requires_ref and model_cfg.reference_text_path is None:
            raise ProviderError(f"referenceTextPath is required for model: {request.model_name}")

        if model_cfg.reference_audio_path is not None:
            reference_audio_path = model_cfg.reference_audio_path
            if not reference_audio_path.is_file():
                raise ProviderError(f"referenceAudioPath not found: {reference_audio_path}")
            copied_reference_name = self._copy_reference_audio(reference_audio_path)
            for node_id in load_audio_node_ids:
                self._set_input_value(prompt, node_id, "audio", copied_reference_name)

        if clone_node_ids and copied_reference_name:
            for node_id in clone_node_ids:
                current = self._get_input_value(prompt, node_id, "reference_audio")
                if isinstance(current, list) and len(current) == 2:
                    continue
                if isinstance(current, str) and current.strip():
                    self._set_input_value(prompt, node_id, "reference_audio", copied_reference_name)
                    continue
                if len(clone_node_ids) == 1 and len(load_audio_node_ids) == 1:
                    self._set_input_value(prompt, node_id, "reference_audio", [load_audio_node_ids[0], 0])
                else:
                    self._set_input_value(prompt, node_id, "reference_audio", copied_reference_name)

        if model_cfg.reference_text_path is not None:
            reference_text_path = model_cfg.reference_text_path
            if not reference_text_path.is_file():
                raise ProviderError(f"referenceTextPath not found: {reference_text_path}")
            reference_text = reference_text_path.read_text(encoding="utf-8-sig").strip()
            if reference_text:
                for node_id in clone_node_ids:
                    self._set_input_value(prompt, node_id, "prompt_text", reference_text)

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
            new_files = [p for p in after_files if p.as_posix() not in before_snapshot]
            recent_files = [p for p in after_files if p.stat().st_mtime >= started_at - 2.0]
            pool = new_files or recent_files or after_files
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

    def _find_node_ids(self, prompt: dict[str, Any], class_name: str) -> list[str]:
        needle = class_name.strip().lower()
        found: list[str] = []
        for node_id, node in prompt.items():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type") or node.get("type") or "").strip().lower()
            if class_type == needle:
                found.append(str(node_id))
        return found

    def _find_save_audio_node_ids(self, prompt: dict[str, Any]) -> list[str]:
        found: list[str] = []
        for node_id, node in prompt.items():
            if not isinstance(node, dict):
                continue
            class_type = str(node.get("class_type") or node.get("type") or "").strip().lower()
            if class_type in _SAVE_AUDIO_CLASSES:
                found.append(str(node_id))
        return found

    def _set_input_value(self, prompt: dict[str, Any], node_id: str, input_key: str, value: Any) -> None:
        node = prompt.get(str(node_id))
        if not isinstance(node, dict):
            raise ProviderError(f"invalid workflow node: {node_id}")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            inputs = {}
            node["inputs"] = inputs
        inputs[input_key] = copy.deepcopy(value)

    def _get_input_value(self, prompt: dict[str, Any], node_id: str, input_key: str) -> Any:
        node = prompt.get(str(node_id))
        if not isinstance(node, dict):
            return None
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            return None
        return inputs.get(input_key)

    def _set_save_audio_basename(self, prompt: dict[str, Any], node_id: str, basename: str) -> None:
        node = prompt.get(node_id)
        if not isinstance(node, dict):
            raise ProviderError(f"invalid workflow node: {node_id}")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            inputs = {}
            node["inputs"] = inputs
        for key in _SAVE_AUDIO_KEYS:
            if key in inputs:
                inputs[key] = basename
                return
        inputs["filename_prefix"] = basename

    def _normalize_voice_description(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
        return normalized or None

    def _wait_history(self, prompt_id: str) -> dict[str, Any]:
        # Override only to support a potentially slower VoxCPM2 pipeline while keeping the same error behavior.
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
