-- 0003 回滚：恢复历史 split 枚举与归档触发器行为。

ALTER TABLE data_samples
    DROP CONSTRAINT IF EXISTS data_samples_dataset_split_check;
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM data_samples WHERE dataset_split IN ('validation', 'test')
    ) THEN
        RAISE EXCEPTION 'cannot roll back 0003 while validation/test sample splits exist';
    END IF;
END;
$$;
ALTER TABLE data_samples
    ADD CONSTRAINT data_samples_dataset_split_check
    CHECK (dataset_split IS NULL OR dataset_split IN ('train', 'query', 'gallery'));

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
