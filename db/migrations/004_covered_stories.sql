-- Persist generated news/video ideas so Glasshouse knows what it has covered
-- and other software can query the same Postgres database.
CREATE TABLE IF NOT EXISTS covered_stories (
    id                  SERIAL PRIMARY KEY,
    analysis_run_id     INTEGER REFERENCES analysis_runs(id),
    transcript_ids      INTEGER[] NOT NULL DEFAULT '{}',
    title               TEXT NOT NULL,
    meeting_source      TEXT,
    hook                TEXT,
    angle               TEXT,
    key_points          JSONB NOT NULL DEFAULT '[]',
    research_queries    JSONB NOT NULL DEFAULT '[]',
    background_research JSONB NOT NULL DEFAULT '[]',
    urgency             TEXT,
    estimated_length    TEXT,
    content_hash        TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'covered',
    idea_json           JSONB NOT NULL,
    covered_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (content_hash)
);

CREATE INDEX IF NOT EXISTS idx_covered_stories_covered_at ON covered_stories(covered_at DESC);
CREATE INDEX IF NOT EXISTS idx_covered_stories_status ON covered_stories(status);
CREATE INDEX IF NOT EXISTS idx_covered_stories_run ON covered_stories(analysis_run_id);
CREATE INDEX IF NOT EXISTS idx_covered_stories_transcripts ON covered_stories USING GIN (transcript_ids);
