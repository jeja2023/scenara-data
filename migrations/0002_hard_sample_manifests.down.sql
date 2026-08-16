-- 0002 回滚：恢复到单条难例承接结构，删除标注快照表与新增索引。

DROP TRIGGER IF EXISTS data_annotation_snapshots_immutable ON data_annotation_snapshots;
DROP FUNCTION IF EXISTS prevent_annotation_snapshot_mutation();
DROP TABLE IF EXISTS data_annotation_snapshots;

DROP INDEX IF EXISTS data_access_grants_version_idx;
DROP INDEX IF EXISTS data_quality_runs_version_idx;
DROP INDEX IF EXISTS data_annotation_tasks_status_idx;
DROP INDEX IF EXISTS data_annotations_sample_idx;

ALTER TABLE data_hard_sample_imports
    DROP CONSTRAINT IF EXISTS data_hard_sample_imports_manifest_scope_key;

ALTER TABLE data_hard_sample_imports
    ADD COLUMN IF NOT EXISTS handoff_id text;

UPDATE data_hard_sample_imports
SET handoff_id = COALESCE(handoff_id, manifest_id)
WHERE handoff_id IS NULL;

ALTER TABLE data_hard_sample_imports
    ALTER COLUMN handoff_id SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'data_hard_sample_imports_tenant_id_project_id_handoff_id_key'
    ) THEN
        ALTER TABLE data_hard_sample_imports
            ADD CONSTRAINT data_hard_sample_imports_tenant_id_project_id_handoff_id_key
            UNIQUE (tenant_id, project_id, handoff_id);
    END IF;
END
$$;

ALTER TABLE data_hard_sample_imports
    DROP COLUMN IF EXISTS manifest_checksum,
    DROP COLUMN IF EXISTS manifest_id;

DROP INDEX IF EXISTS data_samples_split_idx;
ALTER TABLE data_samples DROP COLUMN IF EXISTS dataset_split;
