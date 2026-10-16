SELECT t.id, t.stage, t.credits_reserved, t.credits_charged, t.file_duration_sec, t.engine, t.model_size, t.reserve_reference_id
FROM tasks t
WHERE t.credits_reserved > 0
ORDER BY t.created_at;
