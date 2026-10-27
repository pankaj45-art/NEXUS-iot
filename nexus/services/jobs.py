"""Persisted background jobs and real SSE event delivery (poll fallback in SPA)."""
import json
import threading
import time
import uuid
from .. import db, entitlements
from ..errors import ApiError
from ..providers.base import ProviderError

TERMINAL = {'complete', 'failed', 'cancelled', 'interrupted'}


def uid():
    return str(uuid.uuid4())


def event(conn, jid, kind, data):
    conn.execute('INSERT INTO ai_job_events(job_id,kind,data_json,created_at) VALUES (?,?,?,?)',
                 (jid, kind, json.dumps(data), time.time()))


def current_ent(conn, user_id):
    row = conn.execute('SELECT * FROM users WHERE id=? AND disabled=0', (user_id,)).fetchone()
    if not row:
        raise ApiError(401, 'Account unavailable.', 'unauthorized')
    return entitlements.resolve(conn, row)


def cancelled(conn, jid):
    row = conn.execute('SELECT cancelled FROM ai_jobs WHERE id=?', (jid,)).fetchone()
    return not row or bool(row['cancelled'])


def launch(conn, ent, kind, fn, *, conversation_id=None, message_id=None):
    # Serialize capacity reservation so concurrent HTTP requests cannot bypass
    # per-account/global worker bounds. Network work starts after commit.
    conn.execute('BEGIN IMMEDIATE')
    try:
        if conn.execute("SELECT COUNT(*) FROM ai_jobs WHERE state IN ('queued','running') AND user_id=?", (ent['user_id'],)).fetchone()[0] >= 2:
            raise ApiError(429, 'Two jobs are already running. Cancel or wait before starting another.', 'jobs_busy')
        if conn.execute("SELECT COUNT(*) FROM ai_jobs WHERE state IN ('queued','running')").fetchone()[0] >= 16:
            raise ApiError(503, 'AI worker capacity is busy. Retry shortly.', 'jobs_busy')
        if conversation_id and conn.execute("SELECT 1 FROM ai_jobs WHERE conversation_id=? AND state IN ('queued','running')",(conversation_id,)).fetchone():
            raise ApiError(409,'This conversation already has an active job.','conversation_busy')
        if kind == 'provider_connect':
            active = conn.execute("SELECT id FROM ai_jobs WHERE user_id=? AND kind=? AND state IN ('queued','running')", (ent['user_id'], kind)).fetchone()
            if active:
                raise ApiError(409, 'A connection check is already running. Follow it or cancel it before starting another.', 'connection_busy', {'job_id': active['id']})
        jid, now = uid(), time.time()
        conn.execute("INSERT INTO ai_jobs(id,user_id,conversation_id,message_id,kind,state,created_at,updated_at) VALUES (?,?,?,?,?,'queued',?,?)",
                     (jid, ent['user_id'], conversation_id, message_id, kind, now, now))
        conn.execute('COMMIT')
    except Exception:
        conn.execute('ROLLBACK')
        raise

    def work():
        c = db.connect()
        try:
            if cancelled(c, jid):
                raise ProviderError('cancelled', 'Cancelled before execution.')
            c.execute("UPDATE ai_jobs SET state='running',updated_at=? WHERE id=?", (time.time(), jid))
            event(c, jid, 'status', {'state': 'running', 'kind': kind})
            fresh = current_ent(c, ent['user_id'])
            output = fn(c, fresh, jid)
            if cancelled(c, jid) and not (kind == 'provider_connect' and isinstance(output, dict) and output.get('saved')):
                raise ProviderError('cancelled', 'Cancellation requested; the upstream provider may still charge for completed work.')
            c.execute("UPDATE ai_jobs SET state='complete',output_json=?,updated_at=? WHERE id=?",
                      (json.dumps(output), time.time(), jid))
            event(c, jid, 'done', output)
        except (ProviderError, ApiError) as exc:
            data = exc.payload() if isinstance(exc, ProviderError) else exc.payload()['error']
            state = 'cancelled' if data.get('code') == 'cancelled' else 'failed'
            c.execute('UPDATE ai_jobs SET state=?,error_json=?,updated_at=? WHERE id=?', (state, json.dumps(data), time.time(), jid))
            if message_id:
                c.execute('UPDATE messages SET status=?,meta_json=? WHERE id=?', (state, json.dumps({'error': data}), message_id))
            event(c, jid, 'error', data)
            db.audit(c, ent['user_id'], 'ai.' + state, jid, {'code': data.get('code'), 'kind': kind})
        except Exception as exc:
            # Never write request bodies, provider keys or raw exceptions to logs.
            print('[NEXUS JOB ERROR]', kind, type(exc).__name__, flush=True)
            data = {'code': 'internal_error', 'message': 'The workflow failed unexpectedly. Retry or consult the server logs.', 'retryable': True}
            c.execute("UPDATE ai_jobs SET state='failed',error_json=?,updated_at=? WHERE id=?", (json.dumps(data), time.time(), jid))
            if message_id:
                c.execute("UPDATE messages SET status='failed',meta_json=? WHERE id=?", (json.dumps({'error': data}), message_id))
            event(c, jid, 'error', data)
        finally:
            c.close()
    threading.Thread(target=work, daemon=True, name='nexus-' + kind).start()
    return jid


def get(conn, user_id, jid, after=0):
    r = conn.execute('SELECT * FROM ai_jobs WHERE id=? AND user_id=?', (jid, user_id)).fetchone()
    if not r:
        raise ApiError(404, 'Job not found.', 'not_found')
    events = [{'id': e['id'], 'kind': e['kind'], 'data': json.loads(e['data_json'])} for e in
              conn.execute('SELECT * FROM ai_job_events WHERE job_id=? AND id>? ORDER BY id LIMIT 500', (jid, after))]
    return {'id': r['id'], 'state': r['state'], 'kind': r['kind'], 'cancelled': bool(r['cancelled']),
            'output': json.loads(r['output_json']), 'error': json.loads(r['error_json']),
            'conversation_id': r['conversation_id'], 'message_id': r['message_id'], 'events': events}


class EventStream:
    """Streaming response body. Owns connections; no request Context is retained."""
    def __init__(self, user_id, job_id, after=0):
        self.user_id, self.job_id, self.after = user_id, job_id, after

    def __iter__(self):
        start = time.monotonic()
        c = db.connect()
        try:
            yield b': nexus-stream\n\n'
            while time.monotonic() - start < 150:
                result = get(c, self.user_id, self.job_id, self.after)
                for e in result['events']:
                    self.after = e['id']
                    yield ('id: '+str(e['id'])+'\nevent: '+e['kind']+'\ndata: '+json.dumps(e['data'])+'\n\n').encode()
                if result['state'] in TERMINAL:
                    break
                yield b': heartbeat\n\n'
                time.sleep(0.2)
        finally:
            c.close()


def recover(conn):
    """Called only by server startup, not by schema/bootstrap/config commands."""
    error='{"code":"server_restarted","message":"Server restarted before completion. Retry the request."}'
    conn.execute("UPDATE ai_jobs SET state='interrupted',error_json=? WHERE state IN ('queued','running')",(error,))
    conn.execute("UPDATE messages SET status='interrupted' WHERE status='streaming'")
