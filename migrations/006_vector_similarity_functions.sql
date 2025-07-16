-- Vector similarity search functions for franchise matching

-- Create RPC function for franchise similarity search
CREATE OR REPLACE FUNCTION match_franchises(
  query_embedding vector(384),
  match_threshold float DEFAULT 0.8,
  match_count int DEFAULT 10
)
RETURNS TABLE (
  id uuid,
  canonical_name text,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT 
    f.id,
    f.canonical_name,
    1 - (f.name_embedding <=> query_embedding) as similarity
  FROM franchisors f
  WHERE f.name_embedding IS NOT NULL
    AND 1 - (f.name_embedding <=> query_embedding) >= match_threshold
  ORDER BY f.name_embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Grant execute permission to authenticated users
GRANT EXECUTE ON FUNCTION match_franchises TO authenticated;
GRANT EXECUTE ON FUNCTION match_franchises TO service_role;

-- Create index for better vector search performance if not exists
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes 
    WHERE schemaname = 'public' 
    AND tablename = 'franchisors' 
    AND indexname = 'idx_franchisors_embedding'
  ) THEN
    CREATE INDEX idx_franchisors_embedding ON franchisors 
    USING ivfflat (name_embedding vector_cosine_ops)
    WITH (lists = 100);
  END IF;
END $$;

-- Helper function to update franchise embeddings
CREATE OR REPLACE FUNCTION update_franchise_embedding(
  franchise_id uuid,
  new_embedding vector(384)
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
  UPDATE franchisors 
  SET name_embedding = new_embedding,
      updated_at = now()
  WHERE id = franchise_id;
END;
$$;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION update_franchise_embedding TO authenticated;
GRANT EXECUTE ON FUNCTION update_franchise_embedding TO service_role;