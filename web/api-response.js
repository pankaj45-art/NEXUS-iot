/* Decode backend JSON without leaking raw proxy HTML or declaring an unknown write failed. */
export async function decodeAPIResponse(res) {
  let data;
  try {
    const text = await res.text();
    data = JSON.parse(text);
    if (!data || typeof data !== 'object') throw new Error('Unexpected JSON shape');
  } catch (_) {
    const timeout = [502, 503, 504].includes(res.status);
    const message = `The preview/server returned an unreadable response (HTTP ${res.status}). ` +
      (timeout ? 'The gateway may have timed out while the server was still processing. ' : '') +
      'The outcome is unknown; check the saved connection or recent check before retrying.';
    const e = new Error(message);
    e.status = res.status; e.outcomeUnknown = true;
    e.data = { code: timeout ? 'preview_timeout' : 'invalid_server_response', message, http_status: res.status };
    throw e;
  }
  const responseError = data.error && typeof data.error === 'object' &&
    (data.error.code || data.error.message) && !(data.id && data.state);
  if (!res.ok || responseError) {
    const detail = data.error && typeof data.error === 'object' ? data.error : {};
    const e = new Error(detail.message || `HTTP ${res.status}`);
    e.status = res.status; e.data = detail;
    e.outcomeUnknown = detail.code === 'internal_error';
    throw e;
  }
  return data;
}
