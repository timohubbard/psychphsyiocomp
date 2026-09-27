/**
 * A chest-strap heart-rate reference, over Web Bluetooth.
 *
 * Camera heart rate (the `cardiac` modality, engines/cardiac.rppg_pos) is
 * unvalidated until it has been checked against something that measures the
 * heart directly. A Bluetooth chest strap does — its RR intervals come from
 * the ECG R-peak — and every strap sold for sport speaks the same standard
 * GATT Heart Rate profile, so one parser covers them all. This is how the
 * validation data gets collected: wear a strap during an ordinary session and
 * `npm run verify:rppg` compares the two.
 *
 * The readings travel as ordinary browser chunks under their own source, so
 * the pipeline writes them like any other signal and nothing downstream can
 * mistake them for a camera measurement.
 *
 * Timing: each reading is stamped with performance.now() when the
 * notification arrives. BLE notification latency is tens of milliseconds;
 * the comparison is over 10-second windows, where that is immaterial. It is
 * NOT good enough for beat-to-beat alignment, which is why RR intervals are
 * kept as intervals and not turned into beat times.
 */

export const REFERENCE_SOURCE = 'reference.ble_heart_rate@0.1.0+browser-live';

/** Readings buffered before they are handed on as one chunk. */
const FLUSH_EVERY = 10;

/**
 * Parse a Heart Rate Measurement characteristic value (0x2A37).
 *
 * Byte 0 is flags: bit 0 — HR is uint16 (else uint8); bits 1–2 — sensor
 * contact (bit 2 says the feature is supported, bit 1 that contact is made);
 * bit 3 — an Energy Expended uint16 follows; bit 4 — RR intervals follow, as
 * uint16 in units of 1/1024 s, to the end of the packet. All little-endian.
 *
 * @param {DataView} view
 * @returns {{hr_bpm: number, contact: boolean|null, energy_kj: number|null, rr_ms: number[]}}
 */
export function parseHeartRateMeasurement(view) {
  if (!view || view.byteLength < 2) throw new Error('heart rate packet too short');
  const flags = view.getUint8(0);
  let i = 1;
  let hr;
  if (flags & 0x01) {
    if (view.byteLength < 3) throw new Error('heart rate packet too short for uint16');
    hr = view.getUint16(i, true);
    i += 2;
  } else {
    hr = view.getUint8(i);
    i += 1;
  }
  const contact = (flags & 0x04) ? Boolean(flags & 0x02) : null;
  let energy = null;
  if (flags & 0x08) {
    if (view.byteLength < i + 2) throw new Error('heart rate packet truncated at energy');
    energy = view.getUint16(i, true);
    i += 2;
  }
  const rr = [];
  if (flags & 0x10) {
    for (; i + 1 < view.byteLength; i += 2) rr.push((view.getUint16(i, true) / 1024) * 1000);
  }
  return { hr_bpm: hr, contact, energy_kj: energy, rr_ms: rr };
}

/**
 * Signal rows for one reading. A strap that reports it has lost skin contact
 * sends 0 or a stale value; those readings keep their contact row (so the gap
 * is visible) and lose their rate, rather than being passed on as a heart rate.
 */
export function rowsForReading(reading, ts) {
  const row = (channel, value) => ({
    stream: 'reference', channel, native_clock_id: 'performance.now',
    native_ts: ts, value, reliability_tier: 'high',
  });
  const rows = [];
  if (reading.contact !== null) rows.push(row('reference.contact', reading.contact ? 1 : 0));
  if (reading.contact === false || !(reading.hr_bpm > 0)) return rows;
  rows.push(row('reference.hr_bpm', reading.hr_bpm));
  for (const rr of reading.rr_ms) rows.push(row('reference.rr_ms', rr));
  return rows;
}

/**
 * The connected strap. `onChunk` receives `{source, signals, quality}` chunks,
 * the shape the capture page's live engines already emit.
 */
export class HeartRateStrap {
  constructor({ onChunk, onReading = () => {}, now = () => performance.now() }) {
    this.onChunk = onChunk;
    this.onReading = onReading;
    this.now = now;
    this.buffer = [];
    this.count = 0;
    this.device = null;
    this.characteristic = null;
    this._onValue = (ev) => this.receive(ev.target.value);
  }

  static supported() {
    return typeof navigator !== 'undefined' && Boolean(navigator.bluetooth);
  }

  /** Must be called from a click: the browser shows its own device chooser. */
  async connect() {
    this.device = await navigator.bluetooth.requestDevice({ filters: [{ services: ['heart_rate'] }] });
    const server = await this.device.gatt.connect();
    const service = await server.getPrimaryService('heart_rate');
    this.characteristic = await service.getCharacteristic('heart_rate_measurement');
    this.characteristic.addEventListener('characteristicvaluechanged', this._onValue);
    await this.characteristic.startNotifications();
  }

  receive(view) {
    const ts = this.now();
    const reading = parseHeartRateMeasurement(view);
    this.buffer.push(...rowsForReading(reading, ts));
    this.count += 1;
    this.onReading(reading);
    if (this.count % FLUSH_EVERY === 0) this.flush();
  }

  flush() {
    if (!this.buffer.length) return;
    this.onChunk({ source: REFERENCE_SOURCE, signals: this.buffer, quality: [] });
    this.buffer = [];
  }

  async disconnect() {
    this.flush();
    try {
      this.characteristic?.removeEventListener('characteristicvaluechanged', this._onValue);
      await this.characteristic?.stopNotifications();
    } catch { /* already gone */ }
    this.device?.gatt?.disconnect();
  }
}
