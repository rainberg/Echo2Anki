SELECT id, upload_name, engine, stage, progress, error, started_at, finished_at
FROM tasks WHERE engine='cohere' ORDER BY created_at DESC LIMIT 5;
