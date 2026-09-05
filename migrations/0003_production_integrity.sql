-- 0003：修复生产数据库中版本归档、迁移成员恢复与数据集拆分约束。
-- 此迁移不修改已经登记的历史迁移，因而可安全升级既有数据库。

ALTER TABLE data_samples
    DROP CONSTRAINT IF EXISTS data_samples_dataset_split_check;
ALTER TABLE data_samples
    ADD CONSTRAINT data_samples_dataset_split_check
    CHECK (
        dataset_split IS NULL
        OR dataset_split IN ('train', 'validation', 'test', 'query', 'gallery')
    );

CREATE OR REPLACE FUNCTION protect_published_dataset_version()
RETURNS trigger AS $$
BEGIN
    IF OLD.status = 'archived' THEN
        RAISE EXCEPTION 'archived dataset version is immutable';
    END IF;
    IF OLD.status = 'published' THEN
        -- 唯一允许的变更是 published -> archived，以及归档时间写入。
        IF NEW.status <> 'archived'
           OR NEW.payload ->> 'status' <> 'archived'
           OR NEW.payload ->> 'archived_at' IS NULL
           OR (NEW.payload - ARRAY['status', 'archived_at'])
              IS DISTINCT FROM (OLD.payload - ARRAY['status', 'archived_at']) THEN
            RAISE EXCEPTION 'published dataset version is immutable';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
