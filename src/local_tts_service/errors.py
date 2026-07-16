from __future__ import annotations


class TTSError(Exception):
    """Base error for local TTS service."""


class ConfigError(TTSError):
    """Configuration load/validation error."""


class RequestValidationError(TTSError):
    """Request payload validation error."""


class ProviderError(TTSError):
    """Provider runtime error."""


class NotFoundError(TTSError):
    """Requested resource not found."""
