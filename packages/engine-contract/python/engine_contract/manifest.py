"""Engine contract — Python side.

An engine is a pure, versioned function::

    (media, params) -> signals + events + quality

Engines are deterministic and containerized. An engine knows nothing about the
database, the study runner, or clock alignment. It emits samples stamped with
its OWN native clock; a separate, non-pluggable alignment service fills
``master_ts``. See REPORT.md §3.3.

Keep in sync with ../../src/manifest.ts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Literal, Protocol, Sequence

Modality = Literal["gaze", "face", "voice", "respiration", "cardiac"]
Runtime = Literal["python-gpu", "python-cpu", "wasm", "webgpu"]
Placement = Literal["server-batch", "server-stream", "browser-live"]

#: Per-channel trustworthiness, from the validation evidence — not a UI
#: convention. REPORT.md §2.2: AU12 lands at F1 .72-.83 while AU20 sits at
#: .13-.24. Carrying this in the schema makes it structurally impossible for a
#: rendering layer to present them as equals.
ReliabilityTier = Literal["high", "moderate", "low", "unvalidated"]

CommercialUse = Literal["yes", "no", "unknown"]
MediaKind = Literal["video", "audio"]


@dataclass(frozen=True)
class EngineLicense:
    """Licensing is load-bearing for this project, not metadata.

    This build targets ACADEMIC / NON-PROFIT use, which unlocks OpenFace 3.0,
    LibreFace and openSMILE directly. Several of those are explicitly
    non-commercial. Declaring it per-engine lets ``tools/license-inventory``
    answer "what would we rip out if this went commercial?" at any time.
    """

    spdx: str
    commercial_use: CommercialUse
    url: str
    notes: str | None = None


@dataclass(frozen=True)
class EngineProvenance:
    """Where the weights came from.

    Training-set provenance is the usual reason a permissively-licensed repo
    still cannot ship commercially.
    """

    training_datasets: Sequence[str] = field(default_factory=tuple)
    weights_sha256: str | None = None
    paper_doi: str | None = None


@dataclass(frozen=True)
class InputSpec:
    """Input requirements, enforced by ``probe()`` rather than documented.

    These encode hard findings: rPPG on heavily compressed video performs worse
    than always guessing 75 bpm (§2.4); voice valence is lexically driven and
    dies under noise suppression (§2.3); gaze below ~5 Hz effective sampling is
    excluded by published practice (§5.3).
    """

    kind: MediaKind
    min_fps: float | None = None
    min_width: int | None = None
    min_height: int | None = None
    min_bitrate_kbps: float | None = None
    colorspace: str | None = None
    #: Minimum mean ROI luminance. §2.5: the rPPG skin-tone gap largely closes at >=30.
    min_roi_luminance: float | None = None
    #: getUserMedia constraints that must have been APPLIED at capture time.
    #: We record what was actually applied, not what was requested — the spec
    #: permits a UA to ignore the request without failing (§5.2).
    required_audio_constraints: dict[str, bool] | None = None
    #: Minimum sample rate. Below ~8 kHz a recording has already lost the
    #: fricative energy that distinguishes many consonants, so a transcript of
    #: it is a guess dressed as a reading.
    min_sample_rate_hz: float | None = None
    #: Minimum duration. Separate from the video floors because the failure is
    #: different: a short clip does not merely give a weak estimate, it gets
    #: PADDED to the model's window, and what several models then do is
    #: transcribe or measure the padding.
    min_duration_s: float | None = None


@dataclass(frozen=True)
class SignalSpec:
    channel: str
    unit: str
    #: Nominal rate. Real rate varies per session and is logged as a quality metric.
    nominal_rate_hz: float
    value_type: Literal["float", "int", "bool", "categorical"]
    reliability_tier: ReliabilityTier
    value_range: tuple[float, float] | None = None
    categories: Sequence[str] | None = None
    description: str | None = None


@dataclass(frozen=True)
class EventSpec:
    event_type: str
    description: str | None = None
    has_offset: bool = False


@dataclass(frozen=True)
class QualitySpec:
    metric: str
    unit: str
    description: str | None = None
    #: Published starting points in §5.3: 5 Hz minimum sampling,
    #: 0.5 face-detection confidence.
    warn_below: float | None = None
    warn_above: float | None = None


@dataclass(frozen=True)
class EngineOutputs:
    signals: Sequence[SignalSpec] = field(default_factory=tuple)
    events: Sequence[EventSpec] = field(default_factory=tuple)
    quality: Sequence[QualitySpec] = field(default_factory=tuple)


@dataclass(frozen=True)
class EngineManifest:
    #: Stable, namespaced by modality, e.g. ``resp.chestmotion``.
    engine_id: str
    #: Semver. Appears in every output row via ``source = engine_id@version``.
    version: str
    modality: Modality
    runtime: Runtime
    placement: Placement
    inputs: Sequence[InputSpec]
    params_schema: dict[str, Any]
    outputs: EngineOutputs
    license: EngineLicense
    provenance: EngineProvenance
    determinism: Literal["deterministic", "nondeterministic"] = "deterministic"

    @property
    def source(self) -> str:
        """``source`` column value. Two engines on one modality coexist as rows."""
        return f"{self.engine_id}@{self.version}"


@dataclass(frozen=True)
class Eligibility:
    """Result of ``probe()``. Ineligibility is RECORDED, never a silent skip."""

    eligible: bool
    #: Machine-readable, e.g. ``["bitrate_below_min", "noise_suppression_applied"]``.
    reasons: Sequence[str] = field(default_factory=tuple)
    #: Human-readable, for the quality row and the researcher.
    detail: str | None = None


@dataclass(frozen=True)
class MediaDescriptor:
    """Media handed to an engine, before it decides whether it can run."""

    path: str
    kind: MediaKind
    sha256: str
    #: None when the container does not carry a usable frame count. Optional
    #: because a browser-produced WebM genuinely does not know its own length,
    #: and OpenCV reports that as INT64_MIN rather than as an absence — which
    #: divides into a confident, enormous, negative duration. A nullable field
    #: makes "unknown" representable, so it stops being representable as -9.2e18.
    duration_s: float | None
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    bitrate_kbps: float | None = None
    codec: str | None = None
    applied_audio_constraints: dict[str, bool] | None = None
    mean_roi_luminance: float | None = None
    #: Audio sample rate as the file actually reports it, not as it was
    #: requested. Without this field an engine's sample-rate gate reads
    #: a missing attribute and passes everything, which is how the
    #: transcript engine's floor spent its first hour doing nothing.
    sample_rate_hz: float | None = None
    channels: int | None = None


@dataclass(frozen=True)
class SignalRow:
    stream: str
    channel: str
    native_clock_id: str
    native_ts: float
    value: float | str | bool
    reliability_tier: ReliabilityTier


@dataclass(frozen=True)
class EventRow:
    event_type: str
    native_clock_id: str
    onset_native_ts: float
    offset_native_ts: float | None = None
    stimulus_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class QualityRow:
    stream: str
    metric: str
    window_start_native_ts: float
    window_end_native_ts: float
    value: float


@dataclass(frozen=True)
class Chunk:
    signals: Sequence[SignalRow] = field(default_factory=tuple)
    events: Sequence[EventRow] = field(default_factory=tuple)
    quality: Sequence[QualityRow] = field(default_factory=tuple)


class Engine(Protocol):
    """Every server-side engine implements exactly this."""

    manifest: EngineManifest

    def probe(self, media: MediaDescriptor) -> Eligibility:
        """Can I run on this media? If not, why not?

        Never raise for ineligible-but-valid media — return ``Eligibility`` so
        the caller can write a quality row explaining the gap.
        """
        ...

    def run(self, media: MediaDescriptor, params: dict[str, Any]) -> Iterator[Chunk]:
        """Yield chunks. Must be deterministic given (media, params)."""
        ...
