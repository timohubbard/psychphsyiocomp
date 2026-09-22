/**
 * Session recorder — capture, timestamping, and the event log.
 *
 * The browser's job is capture and timestamping, NOT inference. Inference is a
 * re-runnable server-side job over the stored media. REPORT.md §2.2 is the
 * reason: engine choice swung valid-face-frame yield 43%→63% on identical
 * video, so a pipeline that cannot re-run permanently bakes in whichever engine
 * was current on the day. The live in-browser engine exists for participant
 * feedback only.
 */

import { now, stamp, startSessionClock, measureClockResolution, isCrossOriginIsolated } from './clock.js';

/**
 * Audio constraints requested for research-grade capture.
 *
 * All three browser DSP stages are requested OFF. §2.3 is why: transformer SER
 * valence is driven by implicit lexical content, so noise suppression that
 * degrades intelligibility silently deletes the capability rather than merely
 * adding noise. Constraints are best-effort — the spec explicitly permits a UA
 * to ignore them without failing — so we record what was actually APPLIED, not
 * what we asked for (§5.2).
 */
export const RESEARCH_AUDIO_CONSTRAINTS = {
  echoCancellation: false,
  noiseSuppression: false,
  autoGainControl: false,
  channelCount: 1,
  sampleRate: 48000,
};

export const DEFAULT_VIDEO_CONSTRAINTS = {
  width: { ideal: 1280 },
  height: { ideal: 720 },
  frameRate: { ideal: 30 },
  facingMode: 'user',
};

export class SessionRecorder {
  /**
   * @param {object} opts
   * @param {string} opts.sessionId
   * @param {string} opts.participantId
   * @param {string} [opts.studyId]
   */
  constructor({ sessionId, participantId, studyId = 'default' }) {
    this.sessionId = sessionId;
    this.participantId = participantId;
    this.studyId = studyId;

    this.stream = null;
    this._mediaRecorder = null;
    this._chunks = [];
    this._events = [];
    this._appliedAudioConstraints = null;
    this._appliedVideoSettings = null;
    this._recordingStartedAt = null;
    this._frameStats = { frames: 0, firstTs: null, lastTs: null };
    this._geometry = null;
    this._consent = null;
  }

  // -- capture ---------------------------------------------------------

  async start({ audio = true, video = true } = {}) {
    startSessionClock();

    this.stream = await navigator.mediaDevices.getUserMedia({
      video: video ? DEFAULT_VIDEO_CONSTRAINTS : false,
      audio: audio ? RESEARCH_AUDIO_CONSTRAINTS : false,
    });

    this._recordAppliedConstraints();

    const mimeType = pickMimeType();
    this._mediaRecorder = new MediaRecorder(this.stream, {
      mimeType,
      videoBitsPerSecond: 4_000_000,
    });
    this._mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) this._chunks.push(e.data);
    };

    this._recordingStartedAt = now();
    this._mediaRecorder.start(1000); // 1s chunks, so a crash loses at most 1s

    this.logEvent('recording_start', { mimeType });
    return { mimeType, appliedAudioConstraints: this._appliedAudioConstraints };
  }

  /**
   * Record the constraints the UA ACTUALLY applied.
   *
   * §5.2: `getCapabilities()` reports what a device supports, but constraints
   * are best-effort and OS/driver processing can persist regardless. What was
   * applied determines which voice channels are even valid downstream, so the
   * engine's `probe()` reads this rather than trusting the request.
   */
  _recordAppliedConstraints() {
    const audioTrack = this.stream.getAudioTracks()[0];
    if (audioTrack) {
      const settings = audioTrack.getSettings();
      this._appliedAudioConstraints = {
        echoCancellation: settings.echoCancellation ?? null,
        noiseSuppression: settings.noiseSuppression ?? null,
        autoGainControl: settings.autoGainControl ?? null,
        sampleRate: settings.sampleRate ?? null,
        channelCount: settings.channelCount ?? null,
        // Whether the device would even allow them off, for diagnosis.
        capabilities: typeof audioTrack.getCapabilities === 'function'
          ? safeCapabilities(audioTrack)
          : null,
      };
    }

    const videoTrack = this.stream.getVideoTracks()[0];
    if (videoTrack) {
      const s = videoTrack.getSettings();
      this._appliedVideoSettings = {
        width: s.width ?? null,
        height: s.height ?? null,
        frameRate: s.frameRate ?? null,
        deviceId: undefined, // deliberately not retained — see §6.5
      };
    }
  }

  async stop() {
    if (!this._mediaRecorder) return null;
    this.logEvent('recording_stop');

    const stopped = new Promise((resolve) => {
      this._mediaRecorder.onstop = resolve;
    });
    this._mediaRecorder.stop();
    await stopped;

    this.stream.getTracks().forEach((t) => t.stop());

    const type = this._mediaRecorder.mimeType;
    return new Blob(this._chunks, { type });
  }

  // -- events ----------------------------------------------------------

  /**
   * Log an event on the master clock.
   *
   * These are what the alignment service anchors everything else to, so they
   * are stamped as close to the actual occurrence as possible — the caller
   * should call this at the moment of the event, not afterwards.
   */
  logEvent(eventType, metadata = null, stimulusId = null) {
    const s = stamp();
    this._events.push({
      event_type: eventType,
      onset_native_ts: s.native_ts,
      offset_native_ts: null,
      native_clock_id: s.native_clock_id,
      stimulus_id: stimulusId,
      metadata,
    });
    return s.native_ts;
  }

  /**
   * Record the virtual-chinrest outcome, whether or not it produced geometry.
   *
   * A refused chinrest is recorded exactly as loudly as a successful one. It is
   * the same rule `probe()` follows for engines: ineligibility is a recorded
   * fact, never a silent skip. Without it, a session whose participant never
   * managed the blind-spot task is indistinguishable at analysis time from one
   * where the task was simply never presented — and only one of those is a
   * reason to exclude them.
   *
   * @param {ReturnType<import('./chinrest.js').deriveGeometry>} geometry
   */
  setGeometry(geometry) {
    this._geometry = geometry;
    this.logEvent('virtual_chinrest', {
      ok: geometry.ok,
      geometry_method: geometry.geometry_method,
      viewing_distance_mm: geometry.viewing_distance_mm,
      px_per_mm: geometry.px_per_mm,
      geometry_error_mm: geometry.geometry_error_mm,
      reason: geometry.reason,
      detail: geometry.detail,
    });
    return geometry;
  }

  /**
   * Record the participant's consent decision.
   *
   * Stored whole, not just the tier. "They consented to media retention" is not
   * answerable later without knowing what they were told retention meant, and
   * 45 CFR 46.116 makes retention period and secondary use required elements —
   * so what was disclosed travels with what was agreed.
   */
  setConsent(record) {
    this._consent = record;
    this.logEvent('consent', {
      tier: record?.tier ?? null,
      retention_days: record?.retentionDays ?? null,
    });
    return record;
  }

  /** Close a previously-opened event, e.g. a stimulus that has a duration. */
  closeEvent(eventType, stimulusId = null) {
    for (let i = this._events.length - 1; i >= 0; i -= 1) {
      const e = this._events[i];
      if (e.event_type === eventType && e.offset_native_ts === null
          && (stimulusId === null || e.stimulus_id === stimulusId)) {
        e.offset_native_ts = now();
        return e.offset_native_ts;
      }
    }
    return null;
  }

  get events() {
    return [...this._events];
  }

  // -- frame accounting ------------------------------------------------

  /**
   * Note that a frame was processed, for the achieved-fps quality metric.
   *
   * §2.1 measured webcam sampling at 9-39 fps, jittered several-fold across
   * participants — it is device- and load-dependent and must be MEASURED per
   * session. §5.3 then uses it as a pre-registered exclusion variable, with
   * 5 Hz a published threshold.
   */
  noteFrame(ts = now()) {
    this._frameStats.frames += 1;
    if (this._frameStats.firstTs === null) this._frameStats.firstTs = ts;
    this._frameStats.lastTs = ts;
  }

  achievedFps() {
    const { frames, firstTs, lastTs } = this._frameStats;
    if (frames < 2 || firstTs === null || lastTs <= firstTs) return null;
    return (frames / (lastTs - firstTs)) * 1000;
  }

  // -- output ----------------------------------------------------------

  /** The session.json the server pipeline reads. */
  manifest() {
    return {
      session_id: this.sessionId,
      participant_id: this.participantId,
      study_id: this.studyId,
      events: this.events,
      applied_audio_constraints: this._appliedAudioConstraints,
      video_settings: this._appliedVideoSettings,
      geometry: this._geometry,
      consent: this._consent,
      consent_tier: this._consent?.tier ?? null,
      achieved_fps: this.achievedFps(),
      // Recorded because it bounds what precision was even possible (§3.3).
      clock: {
        master_clock_id: 'performance.now',
        measured_resolution_ms: measureClockResolution(2000),
        cross_origin_isolated: isCrossOriginIsolated(),
      },
      user_agent: navigator.userAgent,
      screen: {
        width_px: window.screen.width,
        height_px: window.screen.height,
        device_pixel_ratio: window.devicePixelRatio,
      },
      created_utc: new Date().toISOString(),
    };
  }
}

function safeCapabilities(track) {
  try {
    const c = track.getCapabilities();
    return {
      echoCancellation: c.echoCancellation ?? null,
      noiseSuppression: c.noiseSuppression ?? null,
      autoGainControl: c.autoGainControl ?? null,
    };
  } catch {
    // getCapabilities only reached cross-browser baseline in Oct 2024; older
    // participant browsers simply will not have it.
    return null;
  }
}

/** Pick the best available container. Codec choice has real consequences. */
export function pickMimeType() {
  // §2.4: on heavily compressed video, rPPG performs worse than always
  // guessing 75 bpm, and H.265 gives by far the best accuracy/bitrate
  // trade-off. Browser H.265 support is uneven, so prefer the least-lossy
  // widely-supported option and record what was actually used.
  const candidates = [
    'video/mp4;codecs=hvc1',       // H.265, best for rPPG if available
    'video/webm;codecs=vp9,opus',
    'video/mp4;codecs=avc1',
    'video/webm;codecs=vp8,opus',
    'video/webm',
  ];
  for (const type of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(type)) {
      return type;
    }
  }
  return 'video/webm';
}
