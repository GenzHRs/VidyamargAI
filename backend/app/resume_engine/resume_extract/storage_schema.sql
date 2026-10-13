PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS documents (
    document_id TEXT PRIMARY KEY,
    source_filename TEXT NOT NULL,
    source_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extractions (
    extraction_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    extraction_schema TEXT NOT NULL,
    original_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    profile_id TEXT PRIMARY KEY,
    extraction_id TEXT NOT NULL REFERENCES extractions(extraction_id),
    mapping_version TEXT NOT NULL,
    mapper_sha256 TEXT NOT NULL,
    full_name TEXT,
    review_status TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_entries (
    profile_id TEXT NOT NULL REFERENCES profiles(profile_id),
    section TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    payload_json TEXT NOT NULL,
    PRIMARY KEY (profile_id, section, ordinal)
);
CREATE INDEX IF NOT EXISTS idx_profiles_name ON profiles(full_name);
CREATE INDEX IF NOT EXISTS idx_entries_section ON profile_entries(section);
