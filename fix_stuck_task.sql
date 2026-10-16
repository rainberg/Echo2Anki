UPDATE tasks SET stage='failed', error='Service restart interrupted task, please retry', finished_at=NOW() WHERE id='f63d2645-57b4-41dc-adc1-92c6f5b1f836';
