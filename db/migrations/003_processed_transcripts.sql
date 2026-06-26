-- Track which meeting transcripts have been analyzed and notified
CREATE TABLE IF NOT EXISTS processed_transcripts (
    transcript_id INTEGER PRIMARY KEY,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analysis_run_id INTEGER REFERENCES analysis_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_processed_transcripts_at ON processed_transcripts(processed_at DESC);
