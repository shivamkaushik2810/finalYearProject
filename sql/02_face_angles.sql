alter table students add column if not exists face_embeddings jsonb default '[]'::jsonb;
