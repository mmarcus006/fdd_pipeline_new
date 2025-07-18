# Edge Functions Documentation

## Overview

Supabase Edge Functions provide a serverless, globally distributed API layer for public access to FDD data. These TypeScript/Deno functions run close to users and integrate seamlessly with Supabase Auth and RLS policies.

## Architecture

```mermaid
graph LR
    A[Client App] --> B[Supabase Edge Functions]
    B --> C[PostgREST API]
    B --> D[PostgreSQL]
    B --> E[Supabase Auth]
    
    subgraph "Edge Functions"
        F[/api/franchisors]
        G[/api/fdds]
        H[/api/search]
        I[/api/analytics]
    end
```

## Available Functions

### 1. Franchisor Search

**Function**: `franchisor-search`  
**Path**: `/api/franchisors/search`  
**Method**: `GET`

Search for franchisors by name with fuzzy matching.

```typescript
// supabase/functions/franchisor-search/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2"

serve(async (req: Request) => {
  const { searchParams } = new URL(req.url)
  const query = searchParams.get('q')
  const limit = parseInt(searchParams.get('limit') || '10')

  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  )

  const { data, error } = await supabase
    .rpc('search_franchisors', { 
      search_query: query,
      result_limit: limit 
    })

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  return new Response(JSON.stringify({ results: data }), {
    headers: { 'Content-Type': 'application/json' },
  })
})
```

**Request Example:**
```bash
curl https://your-project.supabase.co/functions/v1/franchisor-search?q=subway&limit=5
```

**Response:**
```json
{
  "results": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "canonical_name": "Subway Restaurants",
      "parent_company": "Subway IP LLC",
      "latest_fdd_date": "2024-01-15",
      "total_outlets": 20576,
      "similarity_score": 0.98
    }
  ]
}
```

### 2. FDD Data Access

**Function**: `fdd-data`  
**Path**: `/api/fdds/{fdd_id}/item/{item_no}`  
**Method**: `GET`

Retrieve extracted data for specific FDD items.

```typescript
// supabase/functions/fdd-data/index.ts
import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from "https://esm.sh/@supabase/supabase-js@2"

serve(async (req: Request) => {
  const pattern = new URLPattern({ pathname: '/api/fdds/:fdd_id/item/:item_no' })
  const match = pattern.exec(req.url)
  
  if (!match) {
    return new Response('Not Found', { status: 404 })
  }

  const { fdd_id, item_no } = match.pathname.groups
  
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_ANON_KEY')!,
    {
      global: {
        headers: { Authorization: req.headers.get('Authorization')! },
      },
    }
  )

  // Check if item has structured data
  const structuredItems = [5, 6, 7, 19, 20, 21]
  let query
  
  if (structuredItems.includes(parseInt(item_no))) {
    // Query specific table
    const tableName = `item${item_no}_${getTableSuffix(item_no)}`
    query = supabase
      .from(tableName)
      .select('*')
      .eq('section_id', await getSectionId(supabase, fdd_id, item_no))
  } else {
    // Query generic JSON table
    query = supabase
      .from('fdd_item_json')
      .select('data')
      .eq('section_id', await getSectionId(supabase, fdd_id, item_no))
      .single()
  }

  const { data, error } = await query

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  return new Response(JSON.stringify(data), {
    headers: { 
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=3600'
    },
  })
})

function getTableSuffix(itemNo: string): string {
  const suffixes: Record<string, string> = {
    '5': 'initial_fees',
    '6': 'other_fees',
    '7': 'initial_investment',
    '19': 'fpr',
    '20': 'outlet_summary',
    '21': 'financials'
  }
  return suffixes[itemNo] || 'json'
}
```

### 3. Analytics Aggregation

**Function**: `franchise-analytics`  
**Path**: `/api/analytics/growth`  
**Method**: `POST`

Get aggregated analytics across franchises.

```typescript
// supabase/functions/franchise-analytics/index.ts
interface GrowthRequest {
  franchise_ids?: string[]
  start_year: number
  end_year: number
  metrics: ('outlets' | 'revenue' | 'closures')[]
}

serve(async (req: Request) => {
  const body: GrowthRequest = await req.json()
  
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  )

  // Complex aggregation query
  const { data, error } = await supabase.rpc('calculate_growth_metrics', {
    p_franchise_ids: body.franchise_ids,
    p_start_year: body.start_year,
    p_end_year: body.end_year,
    p_metrics: body.metrics
  })

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  return new Response(JSON.stringify({
    period: { start: body.start_year, end: body.end_year },
    data: data
  }), {
    headers: { 
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=300'
    },
  })
})
```

### 4. Webhook Handler

**Function**: `fdd-webhook`  
**Path**: `/api/webhook/fdd-complete`  
**Method**: `POST`

Handle notifications when FDD processing completes.

```typescript
// supabase/functions/fdd-webhook/index.ts
serve(async (req: Request) => {
  // Verify webhook signature
  const signature = req.headers.get('X-Webhook-Signature')
  if (!verifySignature(await req.text(), signature)) {
    return new Response('Unauthorized', { status: 401 })
  }

  const payload = await req.json()
  
  // Trigger downstream processes
  await notifySubscribers(payload.fdd_id)
  await updateSearchIndex(payload.fdd_id)
  await generateSummaryReport(payload.fdd_id)

  return new Response('OK', { status: 200 })
})
```

## Database Functions

Create these PostgreSQL functions to support Edge Functions:

```sql
-- Search franchisors with fuzzy matching
CREATE OR REPLACE FUNCTION search_franchisors(
  search_query TEXT,
  result_limit INT DEFAULT 10
)
RETURNS TABLE (
  id UUID,
  canonical_name TEXT,
  parent_company TEXT,
  latest_fdd_date DATE,
  total_outlets BIGINT,
  similarity_score FLOAT
) AS $$
BEGIN
  RETURN QUERY
  WITH latest_fdds AS (
    SELECT DISTINCT ON (franchise_id) 
      franchise_id,
      issue_date,
      id as fdd_id
    FROM fdds
    WHERE superseded_by_id IS NULL
    ORDER BY franchise_id, issue_date DESC
  ),
  outlet_counts AS (
    SELECT 
      f.franchise_id,
      SUM(os.count_end) as total_outlets
    FROM latest_fdds f
    JOIN fdd_sections fs ON f.fdd_id = fs.fdd_id
    JOIN item20_outlet_summary os ON fs.id = os.section_id
    WHERE os.fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE) - 1
    GROUP BY f.franchise_id
  )
  SELECT 
    f.id,
    f.canonical_name,
    f.parent_company,
    lf.issue_date as latest_fdd_date,
    COALESCE(oc.total_outlets, 0) as total_outlets,
    similarity(f.canonical_name, search_query) as similarity_score
  FROM franchisors f
  LEFT JOIN latest_fdds lf ON f.id = lf.franchise_id
  LEFT JOIN outlet_counts oc ON f.id = oc.franchise_id
  WHERE f.canonical_name % search_query
  ORDER BY similarity_score DESC
  LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- Calculate growth metrics
CREATE OR REPLACE FUNCTION calculate_growth_metrics(
  p_franchise_ids UUID[],
  p_start_year INT,
  p_end_year INT,
  p_metrics TEXT[]
)
RETURNS JSONB AS $$
-- Implementation here
$$ LANGUAGE plpgsql;
```

## Deployment

### 1. Create Edge Function

```bash
# Create new function
supabase functions new franchisor-search

# Deploy function
supabase functions deploy franchisor-search

# Deploy with secrets
supabase functions deploy franchisor-search \
  --env-var CUSTOM_API_KEY=your-key
```

### 2. Configure CORS

```typescript
// Add CORS headers to responses
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
}

return new Response(JSON.stringify(data), {
  headers: { ...corsHeaders, 'Content-Type': 'application/json' },
})
```

### 3. Set Environment Variables

```bash
# Required environment variables (automatically available)
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY

# Custom variables
supabase secrets set SMTP_PASSWORD=your-password
```

## Client Usage

### JavaScript/TypeScript

```typescript
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  'https://your-project.supabase.co',
  'your-anon-key'
)

// Call Edge Function
const { data, error } = await supabase.functions.invoke('franchisor-search', {
  body: { q: 'subway', limit: 5 }
})
```

### React Example

```tsx
function FranchisorSearch() {
  const [results, setResults] = useState([])
  
  const search = async (query: string) => {
    const { data, error } = await supabase.functions.invoke('franchisor-search', {
      body: { q: query }
    })
    
    if (!error) {
      setResults(data.results)
    }
  }
  
  return (
    <div>
      <input onChange={(e) => search(e.target.value)} />
      {results.map(r => (
        <div key={r.id}>{r.canonical_name}</div>
      ))}
    </div>
  )
}
```

### cURL

```bash
curl -X GET \
  'https://your-project.supabase.co/functions/v1/franchisor-search?q=subway' \
  -H 'apikey: your-anon-key' \
  -H 'Authorization: Bearer your-anon-key'
```

## Security Best Practices

### 1. Authentication
- Use Supabase Auth for user authentication
- Validate JWT tokens in Edge Functions
- Apply Row Level Security (RLS) policies

### 2. Rate Limiting
```typescript
// Simple rate limiting with Deno KV
const kv = await Deno.openKv()
const clientIp = req.headers.get('x-forwarded-for')
const key = ['rate-limit', clientIp]
const count = await kv.get(key)

if (count?.value > 100) {
  return new Response('Too Many Requests', { status: 429 })
}

await kv.set(key, (count?.value || 0) + 1, { expireIn: 60000 })
```

### 3. Input Validation
```typescript
import { z } from "https://deno.land/x/zod/mod.ts"

const searchSchema = z.object({
  q: z.string().min(2).max(100),
  limit: z.number().min(1).max(50).default(10)
})

const validated = searchSchema.parse(params)
```

## Monitoring

### 1. Function Logs
```bash
# View function logs
supabase functions logs franchisor-search

# Follow logs
supabase functions logs franchisor-search --follow
```

### 2. Custom Metrics
```typescript
// Log custom metrics
console.log(JSON.stringify({
  event: 'search_performed',
  query: query,
  result_count: data.length,
  duration_ms: Date.now() - startTime
}))
```

### 3. Error Tracking
```typescript
try {
  // Function logic
} catch (error) {
  console.error(JSON.stringify({
    event: 'function_error',
    function: 'franchisor-search',
    error: error.message,
    stack: error.stack,
    timestamp: new Date().toISOString()
  }))
  
  return new Response('Internal Server Error', { status: 500 })
}
```

## Performance Optimization

### 1. Caching
- Use Cache-Control headers
- Implement Deno KV for in-function caching
- Cache database queries at PostgreSQL level

### 2. Connection Pooling
- Reuse Supabase client instances
- Use prepared statements for repeated queries

### 3. Response Compression
```typescript
// Enable gzip compression
const encoder = new TextEncoder()
const data = encoder.encode(JSON.stringify(responseData))
const compressed = await compress(data)

return new Response(compressed, {
  headers: {
    'Content-Type': 'application/json',
    'Content-Encoding': 'gzip'
  }
})
```

## Testing

### Local Development
```bash
# Run function locally
supabase functions serve franchisor-search

# Test locally
curl http://localhost:54321/functions/v1/franchisor-search?q=test
```

### Integration Tests
```typescript
// tests/franchisor-search.test.ts
import { assertEquals } from "https://deno.land/std/testing/asserts.ts"

Deno.test("franchisor search returns results", async () => {
  const response = await fetch(
    "http://localhost:54321/functions/v1/franchisor-search?q=subway"
  )
  
  assertEquals(response.status, 200)
  const data = await response.json()
  assertEquals(Array.isArray(data.results), true)
})
```

---

For internal API documentation, see [Internal API Reference](internal_api.md).