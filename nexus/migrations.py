"""Additive, versioned migrations. Never reseed/overwrite existing user data."""
import time

MIGRATIONS = [(1, """
CREATE TABLE IF NOT EXISTS engineering_projects (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 name TEXT NOT NULL, spec_json TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_design_owner ON engineering_projects(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS engineering_versions (
 id INTEGER PRIMARY KEY, project_id TEXT NOT NULL REFERENCES engineering_projects(id) ON DELETE CASCADE,
 revision INTEGER NOT NULL, spec_json TEXT NOT NULL, summary TEXT NOT NULL, created_at REAL NOT NULL,
 UNIQUE(project_id,revision)
);
CREATE TABLE IF NOT EXISTS conversations (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 project_id TEXT REFERENCES engineering_projects(id) ON DELETE CASCADE,
 title TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversation_owner ON conversations(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 role TEXT NOT NULL, content TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'complete',
 meta_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_message_conversation ON messages(conversation_id,created_at);
CREATE TABLE IF NOT EXISTS ai_jobs (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
 message_id TEXT REFERENCES messages(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, state TEXT NOT NULL, output_json TEXT NOT NULL DEFAULT '{}',
 error_json TEXT NOT NULL DEFAULT '{}', cancelled INTEGER NOT NULL DEFAULT 0,
 created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_owner ON ai_jobs(user_id,created_at);
CREATE TABLE IF NOT EXISTS ai_job_events (
 id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES ai_jobs(id) ON DELETE CASCADE,
 kind TEXT NOT NULL, data_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_job_events ON ai_job_events(job_id,id);
CREATE TABLE IF NOT EXISTS generated_images (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 project_id TEXT REFERENCES engineering_projects(id) ON DELETE SET NULL,
 conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
 message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
 prompt TEXT NOT NULL, mime TEXT NOT NULL, bytes BLOB NOT NULL,
 meta_json TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_image_owner ON generated_images(user_id,created_at);
CREATE TABLE IF NOT EXISTS attachments (
 id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 name TEXT NOT NULL, mime TEXT NOT NULL, text TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS component_definitions (
 model TEXT PRIMARY KEY, definition_json TEXT NOT NULL,
 author_id INTEGER REFERENCES users(id), updated_at REAL NOT NULL
);
""")]


def migrate(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at REAL NOT NULL)')
    for version, sql in MIGRATIONS:
        if not conn.execute('SELECT 1 FROM schema_migrations WHERE version=?', (version,)).fetchone():
            # DDL is idempotent; version recorded only once all statements succeed.
            conn.executescript('BEGIN IMMEDIATE;\n' + sql + '\nINSERT INTO schema_migrations VALUES (' + str(version) + ',' + str(time.time()) + ');\nCOMMIT;')
