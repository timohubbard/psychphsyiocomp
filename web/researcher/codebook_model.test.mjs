import { test } from 'node:test';
import assert from 'node:assert/strict';

import { MAX_ADD, blankCodebook, categoryIdFrom, fmtTime, gridTimes, mergeItems, parseTimes,
  sampleTimes, shuffle } from './codebook_model.js';

test('times are read the ways people write them, and nothing is guessed', () => {
  assert.deepEqual(parseTimes('12, 12.5 12s\n1500ms 1:05 1:05.5 1:02:03'),
    { ms: [12000, 12500, 12000, 1500, 65000, 65500, 3723000], bad: [] });
  assert.deepEqual(parseTimes('0:75 abc 1:2:3 -4').bad, ['0:75', 'abc', '1:2:3', '-4']);
  assert.deepEqual(parseTimes(''), { ms: [], bad: [] });
});

test('moments are whole milliseconds — the key the store files labels under', () => {
  for (const t of parseTimes('0.0004 1.2345 2.5').ms) assert.ok(Number.isInteger(t), String(t));
  for (const t of sampleTimes(0, 10, 5, 0, 7)) assert.ok(Number.isInteger(t), String(t));
});

test('a grid covers its span inclusively and refuses a runaway step', () => {
  assert.deepEqual(gridTimes(10, 30, 5), [10000, 15000, 20000, 25000, 30000]);
  assert.deepEqual(gridTimes(0, 1, 0.3), [0, 300, 600, 900]);
  assert.throws(() => gridTimes(0, 10, 0), /step above zero/);
  assert.throws(() => gridTimes(10, 5, 1), /end after it/);
  assert.throws(() => gridTimes(0, 10000, 1), new RegExp(`more than ${MAX_ADD}`));
});

test('a random sample is reproducible from its seed, in range, in order and spaced', () => {
  const a = sampleTimes(10, 120, 20, 2, 42);
  assert.deepEqual(a, sampleTimes(10, 120, 20, 2, 42));
  assert.notDeepEqual(a, sampleTimes(10, 120, 20, 2, 43));
  assert.equal(a.length, 20);
  assert.ok(a.every((t) => t >= 10000 && t <= 120000));
  for (let i = 1; i < a.length; i += 1) assert.ok(a[i] - a[i - 1] >= 2000 - 1, `${a[i - 1]} → ${a[i]}`);
  assert.throws(() => sampleTimes(0, 10, 20, 1, 1), /do not fit/);
});

test('a seeded shuffle keeps every moment and can be reproduced', () => {
  const items = [1000, 2000, 3000, 4000, 5000, 6000];
  const s = shuffle(items, 9);
  assert.deepEqual([...s].sort((x, y) => x - y), items);
  assert.deepEqual(s, shuffle(items, 9));
  assert.notDeepEqual(s, items);
});

test('adding moments keeps the order already chosen and drops repeats', () => {
  assert.deepEqual(mergeItems([3000, 1000], [1000, 2000, 2000]), { items: [3000, 1000, 2000], repeats: 2 });
});

test('times read back the way they were written', () => {
  assert.equal(fmtTime(65000), '1:05');
  assert.equal(fmtTime(65500), '1:05.5');
  assert.equal(fmtTime(5000), '0:05');
  assert.equal(fmtTime(3723000), '1:02:03');
  for (const t of [0, 1234, 65500, 599999, 3723000]) assert.deepEqual(parseTimes(fmtTime(t)).ms, [t]);
});

test('category ids are slugs, and never collide', () => {
  assert.equal(categoryIdFrom('Eyes closed (blink)'), 'eyes-closed-blink');
  assert.equal(categoryIdFrom('Away', ['away']), 'away-2');
  assert.equal(categoryIdFrom('!!!'), 'category');
});

test('a blank codebook asks for definitions rather than supplying them', () => {
  const cb = blankCodebook();
  assert.equal(cb.categories.length, 2);
  assert.ok(cb.categories.every((c) => c.description === ''));
  assert.deepEqual(cb.items, []);
});
