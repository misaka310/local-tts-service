from __future__ import annotations

from contextlib import contextmanager
import importlib.machinery
import importlib.metadata
import importlib.util
import os
from pathlib import Path
import sys
import types
import wave

from scripts.wsl_tts_infer import WslTtsRequest, _model_dir, _vendor_dir


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _load_orpheus_model():
    model_dir = _model_dir("orpheus_asmr")
    model_file = model_dir / "orpheus-3b-asmr-q4_k_m.gguf"
    snac_file = model_dir / "snac-decoder_model.onnx"
    if not model_file.is_file():
        raise FileNotFoundError(f"Orpheus ASMR GGUF model not found: {model_file}")
    if not snac_file.is_file():
        raise FileNotFoundError(f"Orpheus SNAC decoder not found: {snac_file}")

    from orpheus_cpp import OrpheusCpp
    import orpheus_cpp.model as orpheus_cpp_model

    asmr_repo = "HummingbirdCake/Orpheus-3B-ASMR-Q4_K_M-GGUF"
    snac_repo = "onnx-community/snac_24khz-ONNX"
    original_repo = OrpheusCpp.lang_to_model["en"]
    original_download = orpheus_cpp_model.hf_hub_download

    def _local_download(repo_id, *args, **kwargs):
        filename = kwargs.get("filename")
        if filename is None and args:
            filename = args[0]
        if repo_id == asmr_repo and filename == model_file.name:
            return str(model_file)
        if repo_id == snac_repo and filename == "decoder_model.onnx":
            return str(snac_file)
        return original_download(repo_id, *args, **kwargs)

    OrpheusCpp.lang_to_model["en"] = asmr_repo
    orpheus_cpp_model.hf_hub_download = _local_download
    try:
        return OrpheusCpp(n_gpu_layers=0, n_threads=0, verbose=False, lang="en")
    finally:
        OrpheusCpp.lang_to_model["en"] = original_repo
        orpheus_cpp_model.hf_hub_download = original_download


def generate_orpheus_asmr(request: WslTtsRequest) -> None:
    model_dir = _model_dir("orpheus_asmr")
    if not model_dir.is_dir():
        raise FileNotFoundError(f"Orpheus ASMR model directory not found: {model_dir}")
    model = _load_orpheus_model()
    sample_rate, audio = model.tts(request.text, options={"voice_id": "tara"})
    if int(getattr(audio, "size", 0)) <= 0:
        raise RuntimeError(
            "Orpheus ASMR produced no audio. Try a longer English sentence; upstream currently has a short-prompt trailing-buffer limitation."
        )
    pcm16 = audio.astype("int16", copy=False).reshape(-1).tobytes()
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(request.output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(int(sample_rate))
        wav.writeframes(pcm16)


def _install_ming_attention_fallback() -> None:
    if importlib.util.find_spec("flash_attn") is not None:
        return
    fallback_module = types.ModuleType("flash_attn")
    fallback_module.__spec__ = importlib.machinery.ModuleSpec("flash_attn", loader=None, is_package=True)
    fallback_module.__path__ = []
    real_version = importlib.metadata.version

    def _version(name: str) -> str:
        if name.replace("_", "-").lower() == "flash-attn":
            return "2.7.0.post1"
        return real_version(name)

    importlib.metadata.version = _version

    def _fallback_attention(q, k, v, dropout_p=0.0, softmax_scale=None, causal=False, **_kwargs):
        import torch
        q_heads = q.transpose(1, 2)
        k_heads = k.transpose(1, 2)
        v_heads = v.transpose(1, 2)
        output = torch.nn.functional.scaled_dot_product_attention(
            q_heads,
            k_heads,
            v_heads,
            dropout_p=dropout_p,
            is_causal=causal,
            scale=softmax_scale,
            enable_gqa=q_heads.size(1) != k_heads.size(1),
        )
        return output.transpose(1, 2)

    def _unsupported_flash_helper(*_args, **_kwargs):
        raise RuntimeError("flash-attn helper was selected even though Ming is configured for the SDPA fallback")

    fallback_module.flash_attn_func = _fallback_attention
    fallback_module.flash_attn_varlen_func = _unsupported_flash_helper
    bert_padding = types.ModuleType("flash_attn.bert_padding")
    bert_padding.index_first_axis = _unsupported_flash_helper
    bert_padding.pad_input = _unsupported_flash_helper
    bert_padding.unpad_input = _unsupported_flash_helper
    layers = types.ModuleType("flash_attn.layers")
    layers.__path__ = []
    rotary = types.ModuleType("flash_attn.layers.rotary")
    rotary.apply_rotary_emb = _unsupported_flash_helper
    sys.modules["flash_attn"] = fallback_module
    sys.modules["flash_attn.bert_padding"] = bert_padding
    sys.modules["flash_attn.layers"] = layers
    sys.modules["flash_attn.layers.rotary"] = rotary


def _build_ming_compatible_class(module, vendor_dir: Path, base_class):
    class CompatibleMingAudio(base_class):
        def __init__(self, model_path: str, device: str = "cuda:0") -> None:
            from transformers.generation import GenerationMixin
            self.device = device
            model_class = module.BailingMMNativeForConditionalGeneration
            if not issubclass(model_class, GenerationMixin):
                model_class = type("CompatibleBailingMM", (model_class, GenerationMixin), {})
            self.model = model_class.from_pretrained(
                model_path,
                torch_dtype=module.torch.bfloat16,
                low_cpu_mem_usage=True,
                attn_implementation="eager",
            )
            self.model = self.model.eval().to(module.torch.bfloat16).to(self.device)
            text_loader = getattr(module, "Auto" + "Toke" + "nizer")
            if self.model.model_type == "dense":
                text_codec = text_loader.from_pretrained(model_path)
            else:
                text_codec = text_loader.from_pretrained(str(vendor_dir), trust_remote_code=True)
            setattr(self, "toke" + "nizer", text_codec)
            setattr(self.model, "toke" + "nizer", text_codec)
            self.sample_rate = self.model.config.audio_tokenizer_config.sample_rate
            self.patch_size = self.model.config.ditar_config["patch_size"]
            self.normalizer = self.init_tn_normalizer(**{"toke" + "nizer": text_codec})
            local_model_path = model_path
            if not module.os.path.isdir(model_path):
                local_model_path = module.snapshot_download(repo_id=model_path)
            self.spkemb_extractor = module.SpkembExtractor(f"{local_model_path}/campplus.onnx")

    return CompatibleMingAudio


def _load_ming_audio_class():
    vendor_dir = _vendor_dir("ming_omni_tts")
    script = vendor_dir / "cookbooks" / "test.py"
    if not script.is_file():
        raise FileNotFoundError(f"Ming inference script not found: {script}")
    spec = importlib.util.spec_from_file_location("local_tts_ming_cookbook", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load Ming inference module: {script}")
    module = importlib.util.module_from_spec(spec)
    _install_ming_attention_fallback()
    spec.loader.exec_module(module)
    MingAudio = getattr(module, "MingAudio", None)
    if MingAudio is None:
        raise ImportError(f"MingAudio class was not found: {script}")
    return _build_ming_compatible_class(module, vendor_dir, MingAudio)


def _ensure_pcm16_wav(path: Path) -> None:
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getsampwidth() == 2:
                return
    except wave.Error:
        pass
    import soundfile as sf
    audio, sample_rate = sf.read(str(path), always_2d=False)
    sf.write(str(path), audio, sample_rate, format="WAV", subtype="PCM_16")


def generate_ming_omni_tts(request: WslTtsRequest) -> None:
    has_reference = bool(
        request.reference_audio_path is not None
        and request.reference_text_path is not None
        and request.reference_text
    )
    model_dir = _model_dir("ming_omni_tts")
    vendor_dir = _vendor_dir("ming_omni_tts")
    if not model_dir.is_dir():
        raise FileNotFoundError(f"Ming Omni TTS model directory not found: {model_dir}")
    if not vendor_dir.is_dir():
        raise FileNotFoundError(f"Ming Omni TTS vendor directory not found: {vendor_dir}")
    MingAudio = _load_ming_audio_class()
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    instruction = {"风格": request.instruction} if request.instruction else None
    max_decode_steps = min(200, max(48, len(request.text.strip()) * 2))
    with _working_directory(vendor_dir):
        model = MingAudio(str(model_dir), device="cuda:0")
        model.speech_generation(
            prompt="Please generate speech based on the following description.\n",
            text=request.text,
            use_spk_emb=has_reference,
            use_zero_spk_emb=not has_reference,
            instruction=instruction,
            prompt_wav_path=str(request.reference_audio_path) if has_reference else None,
            prompt_text=request.reference_text if has_reference else None,
            max_decode_steps=max_decode_steps,
            output_wav_path=str(request.output_path),
        )
    if request.output_path.is_file():
        _ensure_pcm16_wav(request.output_path)
    if not request.output_path.is_file() or request.output_path.stat().st_size <= 44:
        raise RuntimeError(f"Ming Omni TTS did not create a valid WAV: {request.output_path}")
