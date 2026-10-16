SELECT id, upload_name, engine, stage, started_at, finished_at,
       EXTRACT(EPOCH FROM (finished_at - started_at)) / 60 AS duration_minutes
FROM tasks WHERE upload_name='TX00_MIC009_20260608_162500_orig.mp3' AND engine='cohere'
ORDER BY created_at DESC LIMIT 5;
