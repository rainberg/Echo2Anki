-- Get the reserve billing records for these unsettled tasks
SELECT br.id, br.task_id, br.action, br.amount, br.balance_after, br.description, br.created_at
FROM billing_records br
WHERE br.action = 'reserve'
  AND br.task_id IN (
    'eb551a51-68c7-4fff-a7ba-3fc932219a42',
    '2062e846-5303-4c06-ba1d-545fd966446b',
    '58ab42d6-01f3-4038-937e-a6cd6f9c4812',
    '9acefbb9-e596-4d40-9616-6a2c9f6f35dc',
    'ad141a2d-dfab-46a9-bec8-7266d6ead30e',
    'f773c387-8000-4415-8f01-3bcb1ae2f95b',
    'f63d2645-57b4-41dc-adc1-92c6f5b1f836'
  )
ORDER BY br.created_at;
