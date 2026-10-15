# Supabase setup for the Vercel app

The Vercel deployment works without Supabase, but Supabase enables persistent
job history and stored output audio.

## 1. Create Supabase project

Create a Supabase project, then open the SQL editor and run:

```sql
-- supabase/schema.sql
```

The schema creates:

- `public.voiceover_jobs`
- Public Storage bucket `voiceovers`
- Service-role-only row policy for job writes

## 2. Vercel environment variables

Set these on the Vercel project:

```bash
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
SUPABASE_STORAGE_BUCKET=voiceovers
ELEVENLABS_API_KEY=YOUR_ELEVENLABS_KEY
# Recommended for worker uploads; if omitted, ELEVENLABS_API_KEY is used as the access secret.
UPLOAD_ACCESS_TOKEN=YOUR_LONG_RANDOM_UPLOAD_SECRET
```

`SUPABASE_SERVICE_ROLE_KEY` must stay server-side only. Do not expose it in the browser.

## 3. Deploy

```bash
cd vercel_frontdoor
npx vercel --prod --yes --scope stephens-projects-8fbc16d0
```

The hosted app will then save completed output MP3s to Supabase Storage and list
recent jobs from `voiceover_jobs`.


## Large audio uploads

Worker-mode uploads do not send WAV/MP3 data through the Vercel function body.
The browser requests short-lived signed upload tickets from
`/api/upload-ticket` and sends each voice sample / target song directly to
Supabase Storage using the TUS resumable protocol.

- Chunks are fixed at 6 MB to match Supabase's current resumable-upload guidance.
- The browser uses the direct `<project-ref>.storage.supabase.co` hostname when
  the normal Supabase project URL allows it to be derived.
- Only storage object paths and metadata are sent to `/api/queue-job`; the
  worker downloads the objects directly from Storage.
- The service-role key remains server-side. The browser receives only
  short-lived signed upload tokens.
- Ticket creation and Supabase worker queue writes require the configured
  `UPLOAD_ACCESS_TOKEN` (or, for backward compatibility, the matching
  server-side `ELEVENLABS_API_KEY`). This blocks anonymous callers from
  minting storage capabilities.
- Tickets are minted one file at a time immediately before upload and each
  upload session has per-file and aggregate byte quotas.
- If a partial batch fails, the browser calls `/api/upload-abort` so staged
  objects are removed instead of being left unclaimed.
- Instant hosted cloning still uses the Vercel request path and therefore keeps
  its smaller source-audio limit. Select worker mode for large reference sets.

Supabase project/bucket file-size limits still apply to each object. If Storage
rejects an otherwise valid large audio file, raise the bucket/project file-size
limit or move worker object storage to an S3-compatible object store; vector
databases and memory stores are not substitutes for binary audio storage.


### Song replacement separation

For `song_replace`, the worker always uses Demucs before voice conversion:
full song -> Demucs vocals/instrumental -> convert the vocal -> remix over the
instrumental. Clean voice-reference clips, already-isolated vocals, and
instrumental-only beats are not separated again.
