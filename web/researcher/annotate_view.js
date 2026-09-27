/**
 * What a rater is shown for one moment: the categories, numbered for the keys
 * they press. Used by the coding page (annotate.js) and by the codebook
 * builder's preview, so the preview is the coding screen rather than a second
 * description of it.
 */

const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/** The category buttons, in codebook order; `chosen` marks the one already picked. */
export function categoriesHtml(categories, chosen = null) {
  return (categories ?? []).map((c, i) => `
      <button class="cat${c.id === chosen ? ' chosen' : ''}" data-id="${esc(c.id)}">
        <span class="key">${i + 1}</span>
        <span>
          <span class="lbl">${esc(c.label)}</span><br>
          <span class="desc">${esc(c.description)}</span>
        </span>
      </button>`).join('');
}

/** The standing instruction under the buttons. */
export const NO_DEFAULT_NOTE = `Nothing is preselected, and there is no "unsure" option. A default is the
      answer a tired coder gives, and one that happens to match the majority
      manufactures agreement that was never there. If a moment genuinely does
      not fit any category, that is a finding about the codebook — stop and
      say so, rather than picking the nearest.`;
