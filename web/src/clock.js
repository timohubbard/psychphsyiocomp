/**
 * Session clock.
 *
 * Everything the capture page stamps uses `performance.now()`, which is the
 * master clock for the whole pipeline. Three reasons, all from REPORT.md §3.3:
 *
 *   - It is monotonic. `Date.now()` is not — an NTP correction or a user
 *     changing the system clock mid-session would silently corrupt every
 *     interval measured against it.
 *   - Its resolution is clamped as a Spectre mitigation (100µs by default,
 *     5µs under cross-origin isolation), which is well below the timing error
 *     that actually matters here.
 *   - Stimulus events are stamped against it, and stimulus-relative timing is
 *     what the science depends on.
 *
 * What this module does NOT do is pretend to reconcile clocks. The video
 * container has its own timebase and `AudioContext.currentTime` is a third
 * clock again; relating them is the alignment service's job, from measured
 * anchors. Doing it here would be the exact per-engine-clock-math bug §3.3
 * warns about.
 */

/** Wall-clock anchor recorded once, so sessions can be located in real time. */
let sessionEpochUtc = null;
let sessionEpochPerf = null;

export function startSessionClock() {
  sessionEpochUtc = new Date().toISOString();
  sessionEpochPerf = performance.now();
  return { sessionEpochUtc, sessionEpochPerf };
}

/** Current master-clock timestamp, in milliseconds. */
export function now() {
  return performance.now();
}

/** A stamp in the shape engines and the writer expect. */
export function stamp() {
  return { native_clock_id: 'performance.now', native_ts: performance.now() };
}

/**
 * Report the clock's actual resolution, measured rather than assumed.
 *
 * Browsers clamp `performance.now()` differently and the clamp changes with
 * cross-origin isolation, so the only honest way to know is to measure it in
 * the session that is actually running. Recorded as session metadata.
 */
export function measureClockResolution(samples = 10000) {
  let smallestDelta = Infinity;
  let prev = performance.now();
  for (let i = 0; i < samples; i += 1) {
    const t = performance.now();
    const delta = t - prev;
    if (delta > 0 && delta < smallestDelta) smallestDelta = delta;
    prev = t;
  }
  return Number.isFinite(smallestDelta) ? smallestDelta : null;
}

export function sessionEpoch() {
  return { utc: sessionEpochUtc, perf: sessionEpochPerf };
}

/**
 * True when the page is cross-origin isolated, which unlocks the finer
 * `performance.now()` clamp. Worth recording: it changes what timing precision
 * the session was even capable of.
 */
export function isCrossOriginIsolated() {
  return typeof crossOriginIsolated !== 'undefined' ? crossOriginIsolated : false;
}
