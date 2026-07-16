"""Backward-compatible exports for the split synthesis workflow."""
from .synthesis import SynthesisOutcome, SynthesisService, merge_chunking_override, split_text_for_chunks, synthesize_chunked

__all__ = ["SynthesisOutcome", "SynthesisService", "merge_chunking_override", "split_text_for_chunks", "synthesize_chunked"]
