-- Find tasks that have reserve billing records but no settle/refund/charge
SELECT t.id, t.stage, t.credits_reserved, t.credits_charged, t.file_duration_sec, t.engine, t.model_size,
       (SELECT COUNT(*) FROM billing_records br WHERE br.task_id = t.id AND br.action = 'reserve') as reserve_count,
       (SELECT COUNT(*) FROM billing_records br WHERE br.task_id = t.id AND br.action IN ('settle', 'refund', 'charge')) as settle_count
FROM tasks t
WHERE EXISTS (SELECT 1 FROM billing_records br WHERE br.task_id = t.id AND br.action = 'reserve')
  AND NOT EXISTS (SELECT 1 FROM billing_records br WHERE br.task_id = t.id AND br.action IN ('settle', 'refund', 'charge'))
ORDER BY t.created_at;
