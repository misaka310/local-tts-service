from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

_VOICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def normalize_voice_id(value: str | None, *, field_name: str = "voiceId") -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > 80:
        raise ValueError(f"{field_name} is too long")
    if "/" in normalized or "\\" in normalized or ".." in normalized:
        raise ValueError(f"{field_name} contains invalid path characters")
    if not _VOICE_ID_RE.fullmatch(normalized):
        raise ValueError(f"{field_name} must use only A-Z, a-z, 0-9, _ or -")
    return normalized


class SpeakRequest(BaseModel):
    text: str = Field(..., description="text to synthesize")
    model: str | None = Field(default=None)
    voice: str | None = Field(default=None)
    voiceId: str | None = Field(default=None)
    referenceVoice: str | None = Field(default=None)
    engine: str | None = Field(default=None)
    caption: str | None = Field(default=None, description="style/caption for supported models")
    styleCaption: str | None = Field(default=None)
    voiceDescription: str | None = Field(default=None, description="voice description for supported models")
    instruction: str | None = Field(default=None)
    requestId: str | None = Field(default=None)
    language: str | None = Field(default=None)
    seed: int | None = Field(default=None)
    speedScale: float | None = Field(default=None, ge=0.5, le=2.0)
    styleStrength: float | None = Field(default=None, ge=1.0, le=6.0)
    chunking: dict[str, Any] | None = Field(default=None)
    format: str = Field(default="wav")

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        normalized = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            raise ValueError("text is empty")
        if len(normalized) > 12000:
            raise ValueError("text is too long; split it before sending")
        return normalized

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        lowered = str(value or "wav").strip().lower()
        if lowered != "wav":
            raise ValueError("currently only wav is supported")
        return lowered

    @field_validator("caption", "styleCaption", "voiceDescription", "instruction", "language")
    @classmethod
    def validate_optional_text(cls, value: str | None, info) -> str | None:  # type: ignore[no-untyped-def]
        if value is None:
            return None
        normalized = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized:
            return None
        if len(normalized) > 4000:
            raise ValueError(f"{info.field_name} is too long; split it before sending")
        return normalized

    @field_validator("voiceId", "referenceVoice")
    @classmethod
    def validate_voice_id(cls, value: str | None) -> str | None:
        return normalize_voice_id(value)

    @field_validator("chunking")
    @classmethod
    def validate_chunking(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("chunking must be an object")
        allowed = {"softChunkChars", "maxChunkChars", "hardLimitChars", "pauseBetweenChunksMs"}
        cleaned: dict[str, Any] = {}
        for key, raw in value.items():
            if key not in allowed:
                continue
            parsed = int(raw)
            limits = (0, 5000) if key == "pauseBetweenChunksMs" else (20, 4000)
            if parsed < limits[0] or parsed > limits[1]:
                raise ValueError(f"{key} is out of range")
            cleaned[key] = parsed
        return cleaned or None


class SpeakResponse(BaseModel):
    ok: bool = True
    requestId: str
    model: str
    runtime: str
    voiceId: str | None = None
    audioUrl: str
    audioPath: str
    seedUsed: int | None = None
    instructionUsed: str | None = None
    available: bool = True
    unavailableReason: str | None = None
    errorMessage: str | None = None
    timings: dict[str, Any] | None = None
    textLength: int
    voiceDescription: str | None = None
    captionInjectionMode: str | None = None


class HealthResponse(BaseModel):
    ok: bool = True
    service: str = "local-tts-service"
    status: str = "healthy"
    host: str
    port: int
    publicBaseUrl: str
    defaultModel: str
    audioOutputDir: str
    availableRuntimes: list[str]
    availableProviders: list[str] = Field(default_factory=list)
    availableModels: list[str]
    availableModelInfo: list["ModelInfo"] = Field(default_factory=list)


class ModelInfo(BaseModel):
    id: str
    label: str
    family: str
    model: str
    runtime: str
    available: bool = True
    enabled: bool = True
    unavailableReason: str | None = None
    modelId: str | None = None
    supportsReferenceVoice: bool = False
    requiresReferenceText: bool = False
    supportsVoiceClone: bool = False
    supportsVoiceDesign: bool = False
    supportsInstruction: bool = False
    supportsLanguage: bool = False
    supportsSeed: bool = False
    supportsSpeedControl: bool = False
    supportsStyleStrength: bool = False
    defaultLanguage: str | None = None
    notes: str | None = None
    executionDevice: str | None = None
    cpuFallback: bool = False
    performanceWarning: str | None = None
    requiresReferenceAudio: bool
    supportsCaption: bool = False
    defaultCaption: str | None = None
    externalCommandKey: str | None = None
    checkpointDir: str | None = None
    requiresTrainedCheckpoint: bool = False
    chunking: dict[str, Any] | None = None
    textSplitMethod: str | None = None


class ModelsResponse(BaseModel):
    ok: bool = True
    models: list[ModelInfo]


class ReferenceVoiceInfo(BaseModel):
    voiceId: str
    displayName: str
    hasReferenceAudio: bool
    hasReferenceText: bool
    enabled: bool = True
    audioDurationSec: float | None = None
    minReferenceDurationSec: float | None = None
    maxReferenceDurationSec: float | None = None
    errorReason: str | None = None


class ReferenceVoicesResponse(BaseModel):
    ok: bool = True
    defaultReferenceVoice: str | None = None
    referenceVoicesDir: str
    voices: list[ReferenceVoiceInfo]


@dataclass(frozen=True)
class WorkflowTargetConfig:
    node_id: str
    input_key: str


@dataclass(frozen=True)
class WorkflowTargetsConfig:
    text: WorkflowTargetConfig | None = None
    caption: WorkflowTargetConfig | None = None
    seed: WorkflowTargetConfig | None = None
    save_audio: WorkflowTargetConfig | None = None
    reference_audio: WorkflowTargetConfig | None = None
    reference_text: WorkflowTargetConfig | None = None


@dataclass(frozen=True)
class ModelConfig:
    runtime: str
    workflow_path: Path | None = None
    label: str | None = None
    family: str | None = None
    model_id: str | None = None
    requires_reference_audio: bool = False
    requires_reference_text: bool = False
    reference_audio_path: Path | None = None
    reference_text_path: Path | None = None
    supports_caption: bool = False
    supports_instruction: bool = False
    supports_language: bool = False
    supports_seed: bool = False
    supports_speed_control: bool = False
    supports_style_strength: bool = False
    supports_voice_clone: bool = False
    supports_voice_design: bool = False
    supports_reference_voice: bool = False
    default_language: str | None = None
    notes: str | None = None
    default_caption: str | None = None
    voice_description: str | None = None
    external_command_key: str | None = None
    checkpoint: Path | None = None
    checkpoint_dir: Path | None = None
    requires_trained_checkpoint: bool = False
    chunking: dict[str, Any] | None = None
    text_split_method: str | None = None
    runtime_options: dict[str, Any] | None = None
    workflow_targets: WorkflowTargetsConfig | None = None


@dataclass(frozen=True)
class AppConfig:
    root_dir: Path
    host: str
    port: int
    public_base_url: str
    default_model: str
    audio_output_dir: Path
    cors_allowed_origins: list[str]
    models: dict[str, ModelConfig]
    runtimes: dict[str, dict[str, Any]]
    stack: dict[str, Any]
    external_services: dict[str, Any]
    frontend: dict[str, Any]
    reference_voices_dir: Path
    default_reference_voice: str | None
    chunking: dict[str, Any]
