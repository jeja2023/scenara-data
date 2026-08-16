CREATE TABLE IF NOT EXISTS data_datasets (
    dataset_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'active', 'archived')),
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (dataset_id, tenant_id, project_id)
);
CREATE INDEX IF NOT EXISTS data_datasets_scope_idx
    ON data_datasets (tenant_id, project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS data_dataset_versions (
    version_id text PRIMARY KEY,
    dataset_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    version text NOT NULL,
    status text NOT NULL CHECK (status IN ('draft', 'building', 'ready', 'published', 'archived', 'failed')),
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (dataset_id, version),
    UNIQUE (version_id, tenant_id, project_id),
    FOREIGN KEY (dataset_id, tenant_id, project_id)
        REFERENCES data_datasets (dataset_id, tenant_id, project_id)
);
CREATE INDEX IF NOT EXISTS data_dataset_versions_scope_idx
    ON data_dataset_versions (tenant_id, project_id, dataset_id, created_at DESC);

CREATE TABLE IF NOT EXISTS data_samples (
    sample_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    created_by text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (sample_id, tenant_id, project_id)
);
CREATE INDEX IF NOT EXISTS data_samples_scope_idx
    ON data_samples (tenant_id, project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS data_dataset_version_samples (
    version_id text NOT NULL,
    sample_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (version_id, sample_id),
    FOREIGN KEY (version_id, tenant_id, project_id)
        REFERENCES data_dataset_versions (version_id, tenant_id, project_id),
    FOREIGN KEY (sample_id, tenant_id, project_id)
        REFERENCES data_samples (sample_id, tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS data_annotation_providers (
    provider_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS data_annotation_tasks (
    task_id text PRIMARY KEY,
    dataset_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (task_id, tenant_id, project_id),
    FOREIGN KEY (dataset_id, tenant_id, project_id)
        REFERENCES data_datasets (dataset_id, tenant_id, project_id)
);
CREATE TABLE IF NOT EXISTS data_annotation_assignments (
    assignment_id text PRIMARY KEY,
    task_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    FOREIGN KEY (task_id, tenant_id, project_id)
        REFERENCES data_annotation_tasks (task_id, tenant_id, project_id)
);
CREATE TABLE IF NOT EXISTS data_annotations (
    annotation_id text PRIMARY KEY,
    sample_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (annotation_id, tenant_id, project_id),
    FOREIGN KEY (sample_id, tenant_id, project_id)
        REFERENCES data_samples (sample_id, tenant_id, project_id)
);
CREATE TABLE IF NOT EXISTS data_annotation_revisions (
    revision_id text PRIMARY KEY,
    annotation_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    revision_number integer NOT NULL CHECK (revision_number > 0),
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (annotation_id, revision_number),
    UNIQUE (revision_id, tenant_id, project_id),
    FOREIGN KEY (annotation_id, tenant_id, project_id)
        REFERENCES data_annotations (annotation_id, tenant_id, project_id)
);
CREATE TABLE IF NOT EXISTS data_annotation_reviews (
    review_id text PRIMARY KEY,
    task_id text NOT NULL,
    revision_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    reviewed_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    FOREIGN KEY (task_id, tenant_id, project_id)
        REFERENCES data_annotation_tasks (task_id, tenant_id, project_id),
    FOREIGN KEY (revision_id, tenant_id, project_id)
        REFERENCES data_annotation_revisions (revision_id, tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS data_quality_rules (
    rule_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS data_quality_runs (
    run_id text PRIMARY KEY,
    version_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (run_id, tenant_id, project_id),
    FOREIGN KEY (version_id, tenant_id, project_id)
        REFERENCES data_dataset_versions (version_id, tenant_id, project_id)
);
CREATE TABLE IF NOT EXISTS data_quality_issues (
    issue_id text PRIMARY KEY,
    run_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    payload jsonb NOT NULL,
    FOREIGN KEY (run_id, tenant_id, project_id)
        REFERENCES data_quality_runs (run_id, tenant_id, project_id)
);
CREATE TABLE IF NOT EXISTS data_quality_reports (
    report_id text PRIMARY KEY,
    version_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    FOREIGN KEY (version_id, tenant_id, project_id)
        REFERENCES data_dataset_versions (version_id, tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS data_lineage_edges (
    lineage_id text PRIMARY KEY,
    source_entity_id text NOT NULL,
    target_entity_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS data_lineage_scope_source_idx
    ON data_lineage_edges (tenant_id, project_id, source_entity_id);
CREATE INDEX IF NOT EXISTS data_lineage_scope_target_idx
    ON data_lineage_edges (tenant_id, project_id, target_entity_id);
CREATE TABLE IF NOT EXISTS data_lineage_snapshots (
    snapshot_id text PRIMARY KEY,
    version_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    FOREIGN KEY (version_id, tenant_id, project_id)
        REFERENCES data_dataset_versions (version_id, tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS data_hard_sample_imports (
    import_id text PRIMARY KEY,
    handoff_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (tenant_id, project_id, handoff_id)
);
CREATE TABLE IF NOT EXISTS data_import_jobs (
    import_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS data_export_jobs (
    export_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS data_dataset_access_grants (
    grant_id text PRIMARY KEY,
    version_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    FOREIGN KEY (version_id, tenant_id, project_id)
        REFERENCES data_dataset_versions (version_id, tenant_id, project_id)
);

CREATE TABLE IF NOT EXISTS data_audit_records (
    audit_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    action text NOT NULL,
    entity_id text NOT NULL,
    occurred_at timestamptz NOT NULL,
    payload jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS data_audit_scope_idx
    ON data_audit_records (tenant_id, project_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS data_outbox_events (
    event_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(),
    delivered_at timestamptz,
    last_error text
);
CREATE INDEX IF NOT EXISTS data_outbox_pending_idx
    ON data_outbox_events (available_at, occurred_at)
    WHERE delivered_at IS NULL;

CREATE TABLE IF NOT EXISTS data_idempotency_records (
    scope text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash text NOT NULL,
    status_code integer NOT NULL,
    response_payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scope, idempotency_key)
);

CREATE TABLE IF NOT EXISTS data_migration_reports (
    migration_id text PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    package_checksum text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (tenant_id, project_id, package_checksum)
);

CREATE OR REPLACE FUNCTION protect_published_dataset_version()
RETURNS trigger AS $$
BEGIN
    IF OLD.status = 'archived' THEN
        RAISE EXCEPTION 'archived dataset version is immutable';
    END IF;
    IF OLD.status = 'published' THEN
        IF NEW.status <> 'archived' OR (NEW.payload - 'status') <> (OLD.payload - 'status') THEN
            RAISE EXCEPTION 'published dataset version is immutable';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS data_dataset_versions_immutable ON data_dataset_versions;
CREATE TRIGGER data_dataset_versions_immutable
BEFORE UPDATE ON data_dataset_versions
FOR EACH ROW EXECUTE FUNCTION protect_published_dataset_version();

CREATE OR REPLACE FUNCTION protect_dataset_version_samples()
RETURNS trigger AS $$
DECLARE
    current_status text;
BEGIN
    SELECT status INTO current_status
    FROM data_dataset_versions
    WHERE version_id = COALESCE(NEW.version_id, OLD.version_id);
    IF current_status <> 'building' THEN
        RAISE EXCEPTION 'dataset version sample membership is mutable only while building';
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS data_dataset_version_samples_mutable ON data_dataset_version_samples;
CREATE TRIGGER data_dataset_version_samples_mutable
BEFORE INSERT OR UPDATE OR DELETE ON data_dataset_version_samples
FOR EACH ROW EXECUTE FUNCTION protect_dataset_version_samples();

CREATE OR REPLACE FUNCTION prevent_annotation_revision_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'annotation revisions are append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS data_annotation_revisions_append_only ON data_annotation_revisions;
CREATE TRIGGER data_annotation_revisions_append_only
BEFORE UPDATE OR DELETE ON data_annotation_revisions
FOR EACH ROW EXECUTE FUNCTION prevent_annotation_revision_mutation();
