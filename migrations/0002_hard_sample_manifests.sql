-- 0002：难例清单批量承接、样本 split 过滤与标注快照。
-- 可重复执行：所有语句都带 IF EXISTS / IF NOT EXISTS 或幂等判断。

ALTER TABLE data_samples
    ADD COLUMN IF NOT EXISTS dataset_split text
        CHECK (dataset_split IS NULL OR dataset_split IN ('train', 'query', 'gallery'));
CREATE INDEX IF NOT EXISTS data_samples_split_idx
    ON data_samples (tenant_id, project_id, dataset_split)
    WHERE dataset_split IS NOT NULL;

-- 难例承接从单条 handoff 升级为清单级批量导入。
ALTER TABLE data_hard_sample_imports
    ADD COLUMN IF NOT EXISTS manifest_id text,
    ADD COLUMN IF NOT EXISTS manifest_checksum text;

UPDATE data_hard_sample_imports
SET manifest_id = COALESCE(manifest_id, handoff_id)
WHERE manifest_id IS NULL
  AND EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_name = 'data_hard_sample_imports' AND column_name = 'handoff_id'
  );

UPDATE data_hard_sample_imports
SET manifest_checksum = COALESCE(manifest_checksum, repeat('0', 64))
WHERE manifest_checksum IS NULL;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'data_hard_sample_imports' AND column_name = 'handoff_id'
    ) THEN
        ALTER TABLE data_hard_sample_imports DROP COLUMN handoff_id;
    END IF;
END
$$;

ALTER TABLE data_hard_sample_imports
    ALTER COLUMN manifest_id SET NOT NULL,
    ALTER COLUMN manifest_checksum SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'data_hard_sample_imports_manifest_scope_key'
    ) THEN
        ALTER TABLE data_hard_sample_imports
            ADD CONSTRAINT data_hard_sample_imports_manifest_scope_key
            UNIQUE (tenant_id, project_id, manifest_id);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS data_annotation_snapshots (
    snapshot_id text PRIMARY KEY,
    version_id text NOT NULL,
    tenant_id text NOT NULL,
    project_id text NOT NULL,
    checksum text NOT NULL,
    created_at timestamptz NOT NULL,
    payload jsonb NOT NULL,
    UNIQUE (snapshot_id, tenant_id, project_id),
    FOREIGN KEY (version_id, tenant_id, project_id)
        REFERENCES data_dataset_versions (version_id, tenant_id, project_id)
);
CREATE INDEX IF NOT EXISTS data_annotation_snapshots_version_idx
    ON data_annotation_snapshots (tenant_id, project_id, version_id);

CREATE INDEX IF NOT EXISTS data_annotations_sample_idx
    ON data_annotations (tenant_id, project_id, sample_id, created_at DESC);
CREATE INDEX IF NOT EXISTS data_annotation_tasks_status_idx
    ON data_annotation_tasks (tenant_id, project_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS data_quality_runs_version_idx
    ON data_quality_runs (tenant_id, project_id, version_id, created_at DESC);
CREATE INDEX IF NOT EXISTS data_access_grants_version_idx
    ON data_dataset_access_grants (tenant_id, project_id, version_id, expires_at DESC);

-- 标注快照一经登记不可修改：发布冻结的标注修订必须可复现。
CREATE OR REPLACE FUNCTION prevent_annotation_snapshot_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'annotation snapshots are immutable';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS data_annotation_snapshots_immutable ON data_annotation_snapshots;
CREATE TRIGGER data_annotation_snapshots_immutable
BEFORE UPDATE OR DELETE ON data_annotation_snapshots
FOR EACH ROW EXECUTE FUNCTION prevent_annotation_snapshot_mutation();
