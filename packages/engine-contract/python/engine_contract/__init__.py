"""Engine contract — shared types for all inference engines."""

from engine_contract.manifest import (
    Chunk,
    Eligibility,
    Engine,
    EngineLicense,
    EngineManifest,
    EngineOutputs,
    EngineProvenance,
    EventRow,
    EventSpec,
    InputSpec,
    MediaDescriptor,
    QualityRow,
    QualitySpec,
    SignalRow,
    SignalSpec,
)
from engine_contract.media import describe_video, mean_luma, sha256_of

__all__ = [
    "describe_video",
    "mean_luma",
    "sha256_of",
    "Chunk",
    "Eligibility",
    "Engine",
    "EngineLicense",
    "EngineManifest",
    "EngineOutputs",
    "EngineProvenance",
    "EventRow",
    "EventSpec",
    "InputSpec",
    "MediaDescriptor",
    "QualityRow",
    "QualitySpec",
    "SignalRow",
    "SignalSpec",
]
