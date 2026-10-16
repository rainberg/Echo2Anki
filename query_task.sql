UPDATE users SET credits = credits + credits_reserved, credits_reserved = 0 WHERE id = 'd57eab64-8945-4b33-9026-f0b717635adb' AND credits_reserved > 0;
