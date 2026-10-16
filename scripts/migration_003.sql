-- Migration 003: push_record_items + public_shares + public_likes + public_collects + tags extension

-- push_record_items
CREATE TABLE IF NOT EXISTS push_record_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    push_record_id UUID NOT NULL REFERENCES push_records(id) ON DELETE CASCADE,
    segment_id UUID NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pushed',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(push_record_id, segment_id)
);
CREATE INDEX IF NOT EXISTS idx_push_record_items_segment ON push_record_items(segment_id);
CREATE INDEX IF NOT EXISTS idx_push_record_items_record ON push_record_items(push_record_id);

-- public_shares
CREATE TABLE IF NOT EXISTS public_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE UNIQUE,
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(200) NOT NULL,
    description TEXT DEFAULT '',
    difficulty VARCHAR(5),
    category VARCHAR(50),
    duration_tier VARCHAR(20),
    cover_url VARCHAR(500) DEFAULT '',
    play_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    collect_count INTEGER DEFAULT 0,
    is_featured BOOLEAN DEFAULT FALSE,
    shared_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_public_shares_user ON public_shares(user_id);
CREATE INDEX IF NOT EXISTS idx_public_shares_difficulty ON public_shares(difficulty);
CREATE INDEX IF NOT EXISTS idx_public_shares_category ON public_shares(category);
CREATE INDEX IF NOT EXISTS idx_public_shares_duration ON public_shares(duration_tier);
CREATE INDEX IF NOT EXISTS idx_public_shares_featured ON public_shares(is_featured) WHERE is_featured = TRUE;
CREATE INDEX IF NOT EXISTS idx_public_shares_shared_at ON public_shares(shared_at DESC);

-- public_likes
CREATE TABLE IF NOT EXISTS public_likes (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    share_id UUID NOT NULL REFERENCES public_shares(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, share_id)
);

-- public_collects
CREATE TABLE IF NOT EXISTS public_collects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    share_id UUID NOT NULL REFERENCES public_shares(id) ON DELETE CASCADE,
    collection_id UUID REFERENCES collections(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, share_id, collection_id)
);
CREATE INDEX IF NOT EXISTS idx_public_collects_user ON public_collects(user_id);
CREATE INDEX IF NOT EXISTS idx_public_collects_share ON public_collects(share_id);

-- tags extension
ALTER TABLE tags ADD COLUMN IF NOT EXISTS is_system BOOLEAN DEFAULT FALSE;
ALTER TABLE tags ADD COLUMN IF NOT EXISTS tag_type VARCHAR(20) DEFAULT 'custom';
