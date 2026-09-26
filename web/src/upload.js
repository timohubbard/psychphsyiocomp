/**
 * Send the session bundle to the study's server, instead of the participant's
 * Downloads folder. The receiving end is server/ingest.py, reached through the
 * capture server's /ingest proxy, which adds the credential.
 *
 * Order matters: session.json first, because the server decides from its
 * consent tier what may follow; the recording last, because it is the largest
 * and everything else is useful even if it fails. Then `complete` seals it.
 */

/** session.json, then small files, then the recording. */
export function uploadOrder(files) {
  const rank = (name) => (name === 'session.json' ? 0 : name.startsWith('capture.') ? 2 : 1);
  return [...files].sort((a, b) => rank(a.name) - rank(b.name));
}

/** Is uploading available from this page? */
export async function uploadAvailable(fetchFn = fetch) {
  try {
    const res = await fetchFn('/ingest/health', { cache: 'no-store' });
    return res.ok;
  } catch {
    return false;
  }
}

/** PUT one file, reporting bytes sent. XHR because fetch reports no upload progress. */
function put(url, blob, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('PUT', url);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded); };
    xhr.onload = () => (xhr.status === 200 ? resolve()
      : reject(new Error(`${url}: ${xhr.status} ${safeError(xhr.responseText)}`)));
    xhr.onerror = () => reject(new Error(`${url}: network error`));
    xhr.send(blob);
  });
}

function safeError(text) {
  try { return JSON.parse(text).error ?? text; } catch { return text; }
}

/**
 * Upload every file, then seal. `onProgress(fraction, label)` for the page.
 * Rejects with the server's own reason, which is shown to the participant.
 */
export async function uploadBundle(sessionId, files, onProgress = () => {}) {
  const ordered = uploadOrder(files);
  const total = ordered.reduce((n, f) => n + f.blob.size, 0) || 1;
  let done = 0;
  for (const f of ordered) {
    await put(`/ingest/${encodeURIComponent(sessionId)}/${f.name}`, f.blob,
      (sent) => onProgress((done + sent) / total, f.name));
    done += f.blob.size;
    onProgress(done / total, f.name);
  }
  const res = await fetch(`/ingest/${encodeURIComponent(sessionId)}/complete`, { method: 'POST' });
  if (!res.ok) throw new Error(`complete: ${res.status} ${safeError(await res.text())}`);
  return res.json();
}
