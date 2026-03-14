-- TrustVault QA Agent — Database Schema
-- Run this to initialize the PostgreSQL database

CREATE TABLE IF NOT EXISTS qa_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    milestone_id INTEGER NOT NULL,
    submission_hash VARCHAR(64) NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tier VARCHAR(1) NOT NULL DEFAULT '2',
    completion_score FLOAT NOT NULL,
    status VARCHAR(30) NOT NULL,
    confidence FLOAT NOT NULL,
    requires_human_review BOOLEAN NOT NULL DEFAULT FALSE,
    report_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(milestone_id, submission_hash)
);

CREATE TABLE IF NOT EXISTS domain_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evaluation_id UUID REFERENCES qa_evaluations(id),
    domain VARCHAR(10) NOT NULL,
    agent_confidence FLOAT NOT NULL,
    tool_results JSONB NOT NULL,
    criteria_results JSONB NOT NULL,
    warnings TEXT[],
    reasoning_trace TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL,
    milestone_id INTEGER,
    evaluation_id UUID,
    payload JSONB NOT NULL DEFAULT '{}',
    emitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evaluations_milestone ON qa_evaluations(milestone_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_hash ON qa_evaluations(submission_hash);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
