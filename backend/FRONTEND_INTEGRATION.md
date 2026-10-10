# ContextLens Frontend Integration Guide

This guide explains how to connect the React/Vite frontend to the deployed ContextLens AWS backend. It reflects the current backend handlers, result validator, SAM template, tests, and `frontend/src/services/api.js` implementation.

## 1. Backend overview

ContextLens accepts an original MP4 video and a shorter MP4 clip. It transcribes both videos, finds the clip transcript inside the original transcript, and returns the matching timestamps plus the transcript before, during, and after the match. Optional Gemini processing can add a neutral context insight and evidence-based context flags.

The deployed AWS flow is:

1. API Gateway receives create, completion, and status requests.
2. Two small Lambda functions create analysis records, issue upload URLs, queue work, and return status.
3. The browser uploads both videos directly to a private S3 bucket using temporary presigned URLs.
4. SQS delivers completed upload jobs to the container-based analysis worker.
5. The worker uses FFmpeg and Faster-Whisper, performs matching, and optionally requests Gemini insights.
6. DynamoDB stores the operational state and final result.
7. The frontend polls API Gateway until processing reaches a terminal state.

The frontend communicates directly with only:

- API Gateway, for the three JSON endpoints documented below.
- S3, for the two presigned `PUT` uploads.

The frontend does **not** communicate directly with Lambda, SQS, DynamoDB, Secrets Manager, or Gemini.

## 2. Getting started

### Prerequisites

- Node.js and npm.
- The ContextLens repository.
- Two local MP4 files: the full original and the shorter clip.
- The deployed backend base URL:

```text
https://q21qw3hoc9.execute-api.us-east-1.amazonaws.com
```

AWS credentials are **not required** in the browser or for normal frontend development. API Gateway provides the public API, and the backend returns temporary S3 upload authorization inside each presigned URL.

### Dependencies

The API service uses the browser's built-in `fetch`, `AbortController`, and `File` APIs. No additional npm package is required for backend communication.

Install the existing frontend dependencies and start Vite:

```bash
cd frontend
npm install
npm run dev
```

The deployed CORS configuration currently permits the exact origin `http://localhost:5173`, so use Vite's default host and port while developing.

### Configure the API URL

`frontend/src/services/api.js` already defaults to the deployed API URL. To configure it explicitly, create a local `frontend/.env.local` file:

```dotenv
VITE_CONTEXTLENS_API_URL=https://q21qw3hoc9.execute-api.us-east-1.amazonaws.com
```

Restart the Vite development server after changing an environment variable. Vite exposes variables prefixed with `VITE_` to browser code, so never put secrets or AWS credentials in them.

## 3. API reference

All API responses use JSON. Error responses normally use this shape:

```json
{
  "error": "Human-readable error message."
}
```

API Gateway may return its own `{ "message": "..." }` response for gateway-level errors such as an unknown route or throttling.

### `POST /analyses`

Creates an analysis record and returns two presigned S3 upload instructions.

**URL**

```text
POST https://q21qw3hoc9.execute-api.us-east-1.amazonaws.com/analyses
```

**Required request header**

```http
Content-Type: application/json
```

**Request body**

```json
{
  "original": {
    "filename": "full-interview.mp4",
    "content_type": "video/mp4"
  },
  "clip": {
    "filename": "short-clip.mp4",
    "content_type": "video/mp4"
  },
  "use_ai": true
}
```

`use_ai` is optional and defaults to `true`, but it must be a JSON boolean when supplied. Both descriptors and filenames are required. Both filenames must end in `.mp4`, case-insensitively, and both content types must be exactly `video/mp4`.

**Success: HTTP 201**

```json
{
  "analysis_id": "00000000-0000-0000-0000-000000000000",
  "state": "AWAITING_UPLOADS",
  "uploads": {
    "original": {
      "url": "https://example-bucket.s3.amazonaws.com/temporary-signed-value",
      "method": "PUT",
      "headers": {
        "Content-Type": "video/mp4",
        "x-amz-server-side-encryption": "AES256"
      }
    },
    "clip": {
      "url": "https://example-bucket.s3.amazonaws.com/temporary-signed-value",
      "method": "PUT",
      "headers": {
        "Content-Type": "video/mp4",
        "x-amz-server-side-encryption": "AES256"
      }
    }
  },
  "expires_in": 900
}
```

The example URLs above are placeholders. A real response contains temporary signed query parameters and must not be logged or shared.

**Possible errors**

| HTTP status | Meaning |
| --- | --- |
| `400` | Invalid JSON, non-object JSON, a missing descriptor or filename, a non-MP4 filename, a content type other than `video/mp4`, or a non-boolean `use_ai`. |
| `429` | API Gateway throttled the request. Wait and retry with backoff. |
| `500` | The request could not be completed because of an unexpected backend error. |

**JavaScript**

```js
const response = await fetch(`${apiBaseUrl}/analyses`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    original: {
      filename: originalFile.name,
      content_type: 'video/mp4',
    },
    clip: {
      filename: clipFile.name,
      content_type: 'video/mp4',
    },
    use_ai: true,
  }),
})
```

Prefer the existing `createAnalysis` service function instead of duplicating this raw request in components.

### `POST /analyses/{analysis_id}/complete`

Tells the backend that both direct-to-S3 uploads have finished. The backend verifies both uploaded objects and queues the analysis.

**URL**

```text
POST https://q21qw3hoc9.execute-api.us-east-1.amazonaws.com/analyses/{analysis_id}/complete
```

No request body or request header is required. Do not send the videos through this endpoint.

**Success: HTTP 202**

```json
{
  "analysis_id": "00000000-0000-0000-0000-000000000000",
  "state": "QUEUED"
}
```

For an already-processing or terminal analysis, the idempotent response remains HTTP 202 and may contain `PROCESSING`, `COMPLETE`, or `FAILED`. The frontend should normally call completion only once after both S3 requests succeed.

**Possible errors**

| HTTP status | Meaning |
| --- | --- |
| `400` | An uploaded object is empty, exceeds the configured limit, or was uploaded with the wrong content type. |
| `404` | The analysis ID does not exist or has expired. |
| `409` | One or both S3 uploads do not exist yet. Finish both uploads before retrying. |
| `429` | API Gateway throttled the request. |
| `500` | An unexpected backend error prevented validation or queueing. |

**JavaScript**

```js
const response = await fetch(
  `${apiBaseUrl}/analyses/${encodeURIComponent(analysisId)}/complete`,
  { method: 'POST' },
)
```

The existing `completeAnalysis(analysisId)` function implements this request.

### `GET /analyses/{analysis_id}`

Returns the current operational state and, after successful processing, the final result.

**URL**

```text
GET https://q21qw3hoc9.execute-api.us-east-1.amazonaws.com/analyses/{analysis_id}
```

No request body or special header is required.

**Non-terminal response: HTTP 200**

```json
{
  "analysis_id": "00000000-0000-0000-0000-000000000000",
  "state": "PROCESSING",
  "result": null
}
```

**Completed response: HTTP 200**

```json
{
  "analysis_id": "00000000-0000-0000-0000-000000000000",
  "state": "COMPLETE",
  "result": {
    "analysis_id": "00000000-0000-0000-0000-000000000000",
    "created_at": "2026-10-10T11:30:58.151644+00:00",
    "status": "MATCH_FOUND",
    "clip_transcript": "Example clip transcript.",
    "original_duration": 135.21,
    "clip_duration": 5.82,
    "similarity": 100.0,
    "second_best_similarity": 53.79,
    "score_gap": 46.21,
    "threshold": 80.0,
    "match": {
      "start": 83.88,
      "end": 89.9,
      "matched_text": "example normalized matched text",
      "candidate_word_count": 16,
      "clip_word_count": 16
    },
    "context": {
      "before": "Transcript before the match.",
      "during": "Transcript during the match.",
      "after": "Transcript after the match.",
      "word_timestamps": {
        "before": [
          { "word": "Transcript", "start": 68.88, "end": 69.12 }
        ],
        "during": [
          { "word": "Transcript", "start": 83.88, "end": 84.56 }
        ],
        "after": [
          { "word": "Transcript", "start": 89.9, "end": 90.96 }
        ]
      },
      "window": {
        "start": 68.88,
        "end": 104.9,
        "seconds_before": 15,
        "seconds_after": 15
      }
    },
    "context_flags": [],
    "error": null,
    "ai_context_insights": {
      "status": "unavailable",
      "insight": null,
      "model": null
    }
  }
}
```

**Worker failure response: HTTP 200**

```json
{
  "analysis_id": "00000000-0000-0000-0000-000000000000",
  "state": "FAILED",
  "result": null,
  "error": "Analysis processing failed. Please try again."
}
```

**Possible errors**

| HTTP status | Meaning |
| --- | --- |
| `404` | The analysis ID does not exist or the record has expired. |
| `429` | API Gateway throttled the polling request. Back off rather than polling faster. |
| `500` | The status request encountered an unexpected backend error. |

## 4. Video upload workflow

Follow these steps in order:

1. Collect two browser `File` objects: the full original and the short clip.
2. Call `POST /analyses` with their filenames, `video/mp4`, and the `use_ai` boolean.
3. Save the returned `analysis_id` and the two `uploads` instructions in component state only as long as necessary.
4. Upload the original file to `uploads.original.url`.
5. Upload the clip file to `uploads.clip.url`.
6. Wait until **both** uploads return a successful HTTP status.
7. Call `POST /analyses/{analysis_id}/complete` once.
8. Poll `GET /analyses/{analysis_id}` until the top-level state is `COMPLETE` or `FAILED`.
9. Display `result` only when the state is `COMPLETE`.

Each S3 request must copy the returned instruction exactly:

```js
await fetch(upload.url, {
  method: 'PUT',
  headers: {
    'Content-Type': 'video/mp4',
    'x-amz-server-side-encryption': 'AES256',
  },
  body: file,
})
```

Do not add an AWS `Authorization` header. Do not convert the file to JSON, Base64, or `FormData`. Send the `File` as the raw request body. The existing service uses `upload.headers` directly so its headers always match the signature.

Confirmed upload requirements:

- Format: MP4 only.
- Filename: must end in `.mp4`, case-insensitively.
- S3 object content type: exactly `video/mp4`.
- Maximum size per uploaded object: `262144000` bytes (250 MiB).
- Empty files are rejected during completion.
- Presigned URL lifetime: 900 seconds (15 minutes).
- Required encryption header: `x-amz-server-side-encryption: AES256`.
- The backend verifies object existence, size, and metadata before queueing.
- FFmpeg performs the real media/audio validation during asynchronous processing. A file named `.mp4` that is not valid media can therefore upload successfully and later produce `result.status: "ERROR"`.

The original and clip uploads may run concurrently. If either upload fails, do not call the completion endpoint. Request a new analysis if the URL has expired; the current API does not refresh an existing upload URL.

Uploaded demo objects expire from S3 after two days. DynamoDB analysis records use a two-day TTL as configured for the deployed stack, but DynamoDB TTL deletion is asynchronous and is not guaranteed to occur at the exact expiration second.

## 5. Analysis states

The top-level `state` describes the asynchronous AWS job lifecycle:

| State | Meaning | Recommended frontend behavior |
| --- | --- | --- |
| `AWAITING_UPLOADS` | The record exists, but completion has not successfully queued it. | Upload both files. If completion already ran, surface an upload/completion problem instead of polling forever. |
| `QUEUED` | The backend accepted completion and placed the job on SQS. | Show a queued indicator and continue polling. |
| `PROCESSING` | The worker claimed the job and is analyzing the videos. | Show processing progress as indeterminate and continue polling. |
| `COMPLETE` | The worker saved a valid 15-field result. | Stop polling and inspect `result.status`. |
| `FAILED` | The worker failed operationally after its retry behavior. | Stop polling, show the top-level `error`, and let the user start a new analysis. |

Recommended polling behavior:

- Use the existing `pollAnalysis` helper, which defaults to every 2 seconds.
- Do not poll multiple times concurrently for the same analysis.
- Treat `COMPLETE` and `FAILED` as the only terminal processing states.
- Use a timeout and offer a manual retry/status refresh instead of automatically starting another paid analysis.
- The service default timeout is 15 minutes, matching the worker's configured Lambda timeout. Queue wait time can make the overall elapsed time longer, so a polling timeout does not prove that the backend job failed.
- On HTTP 429 or a transient network error, use bounded exponential backoff rather than tightening the interval.

`pollAnalysis` returns both terminal envelopes. It does not throw merely because the state is `FAILED`; the caller must check the returned state. It throws `ApiError` for HTTP/protocol errors and `PollingTimeoutError` when its client-side timeout expires.

## 6. Result response

The final `result` always has exactly these 15 top-level fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `analysis_id` | string | Analysis identifier shared with the polling envelope. |
| `created_at` | string | UTC ISO-8601 timestamp created by the analysis pipeline. |
| `status` | string | One of the four matching result statuses below. |
| `clip_transcript` | string or null | Faster-Whisper transcript of the supplied clip. |
| `original_duration` | number or null | Original audio duration in seconds. |
| `clip_duration` | number or null | Clip audio duration in seconds. |
| `similarity` | number or null | Best transcript similarity score. |
| `second_best_similarity` | number or null | Score for the second-best non-overlapping candidate. |
| `score_gap` | number or null | Best score minus second-best score. |
| `threshold` | number | Matching threshold; currently `80.0`. |
| `match` | object or null | Selected match details; present only for `MATCH_FOUND`. |
| `context` | object or null | Transcript context; present only for `MATCH_FOUND`. |
| `context_flags` | array | Validated AI flags. Empty unless a successful AI response supports flags for a match. |
| `error` | object or null | Result-level code and message. Null only for `MATCH_FOUND`. |
| `ai_context_insights` | object | Optional Gemini status, insight, and model. Always present. |

### Matching result statuses

`result.status` is separate from the top-level processing `state`.

| Result status | Meaning |
| --- | --- |
| `MATCH_FOUND` | The best score meets the threshold and is sufficiently distinct. `match` and `context` are populated; `error` is null. |
| `NO_MATCH` | No candidate reached the similarity threshold. `match` and `context` are null, and `error.code` is `NO_MATCH`. |
| `AMBIGUOUS_MATCH` | Multiple strong candidates are too close to choose reliably. `match` and `context` are null, and `error.code` is `AMBIGUOUS_MATCH`. |
| `ERROR` | Media validation, transcription, input validation, or another handled pipeline step failed. `match` and `context` are null, and `error` explains the result. |

A successfully executed pipeline returns top-level `state: "COMPLETE"` even when `result.status` is `NO_MATCH`, `AMBIGUOUS_MATCH`, or `ERROR`. Top-level `state: "FAILED"` is reserved for an operational worker failure after retry handling and may have `result: null`.

### `match` schema

```json
{
  "start": 83.88,
  "end": 89.9,
  "matched_text": "normalized matched transcript",
  "candidate_word_count": 16,
  "clip_word_count": 16
}
```

`start` and `end` are seconds from the beginning of the original video.

### `context` schema

```json
{
  "before": "Joined transcript before the match.",
  "during": "Joined transcript during the match.",
  "after": "Joined transcript after the match.",
  "word_timestamps": {
    "before": [{ "word": "example", "start": 70.1, "end": 70.5 }],
    "during": [{ "word": "example", "start": 83.88, "end": 84.2 }],
    "after": [{ "word": "example", "start": 89.9, "end": 90.3 }]
  },
  "window": {
    "start": 68.88,
    "end": 104.9,
    "seconds_before": 15,
    "seconds_after": 15
  }
}
```

### Context flags

Each flag has exactly this structure:

```json
{
  "type": "CONTRAST_OR_CORRECTION",
  "title": "Contextual contrast",
  "explanation": "Neutral explanation grounded in the transcript.",
  "evidence": "Short exact transcript evidence."
}
```

Allowed flag types are:

- `ATTRIBUTION_CHANGE`
- `NEGATION_OR_REVERSAL`
- `QUALIFIER_REMOVED`
- `CONDITION_REMOVED`
- `UNCERTAINTY_REMOVED`
- `QUESTION_AS_STATEMENT`
- `CONTRAST_OR_CORRECTION`

An empty `context_flags` array is valid and should not be presented as an error.

### AI insight schema

Available:

```json
{
  "status": "success",
  "insight": "A short neutral explanation.",
  "model": "gemini-3.8-flash"
}
```

Unavailable:

```json
{
  "status": "unavailable",
  "insight": null,
  "model": null
}
```

### Result-level error schema

```json
{
  "code": "NO_MATCH",
  "message": "No sufficiently similar excerpt was found in the original recording."
}
```

Do not assume every error code is only `NO_MATCH`; handled pipeline errors include missing/empty media, invalid media, insufficient speech, transcription failure, ambiguous matches, and general processing errors.

## 7. React integration examples

The existing service is located at `frontend/src/services/api.js` and exports:

- `createAnalysis({ original, clip, useAi }, { signal }?)`
- `uploadVideo(file, upload, { signal }?)`
- `uploadAnalysisVideos({ original, clip }, uploads, { signal }?)`
- `completeAnalysis(analysisId, { signal }?)`
- `getAnalysis(analysisId, { signal }?)`
- `pollAnalysis(analysisId, options?)`
- `ANALYSIS_STATES`, `TERMINAL_ANALYSIS_STATES`, `ApiError`, and `PollingTimeoutError`

### Complete workflow in an Analyze page

```jsx
import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ANALYSIS_STATES,
  ApiError,
  PollingTimeoutError,
  completeAnalysis,
  createAnalysis,
  pollAnalysis,
  uploadAnalysisVideos,
} from '../services/api'

export default function Analyze() {
  const navigate = useNavigate()
  const controllerRef = useRef(null)
  const [state, setState] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleAnalyze(original, clip) {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    setBusy(true)
    setError('')

    try {
      const created = await createAnalysis(
        { original, clip, useAi: true },
        { signal: controller.signal },
      )
      setState(created.state)

      await uploadAnalysisVideos(
        { original, clip },
        created.uploads,
        { signal: controller.signal },
      )

      const queued = await completeAnalysis(created.analysis_id, {
        signal: controller.signal,
      })
      setState(queued.state)

      const finished = await pollAnalysis(created.analysis_id, {
        intervalMs: 2_000,
        timeoutMs: 15 * 60 * 1_000,
        signal: controller.signal,
        onUpdate: (analysis) => setState(analysis.state),
      })

      if (finished.state === ANALYSIS_STATES.FAILED) {
        setError(finished.error || 'Analysis processing failed. Please try again.')
        return
      }

      navigate(`/results/${created.analysis_id}`, {
        state: { analysis: finished },
      })
    } catch (requestError) {
      if (requestError.name === 'AbortError') return

      if (requestError instanceof PollingTimeoutError) {
        setError('Analysis is taking longer than expected. Try checking it again.')
      } else if (requestError instanceof ApiError) {
        setError(requestError.message)
      } else {
        setError('Could not complete the analysis request.')
      }
    } finally {
      setBusy(false)
    }
  }

  function cancelAnalysisRequest() {
    controllerRef.current?.abort()
  }

  // Connect handleAnalyze and cancelAnalysisRequest to your existing UI.
  return null
}
```

Aborting the browser request does not cancel a job already queued in AWS. It only stops the browser upload/request/polling work. Do not automatically create a replacement analysis after an abort because the original job may still be running.

The current frontend pages are placeholders and the router is not yet configured. The navigation example assumes the frontend developer adds a route such as `/results/:analysisId`; that route is a frontend concern, not a backend endpoint.

### Load or refresh a Results page

Navigation state disappears on a full browser refresh. A Results page should fall back to the route parameter:

```jsx
import { useEffect, useState } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { ANALYSIS_STATES, getAnalysis } from '../services/api'

export default function Results() {
  const { analysisId } = useParams()
  const location = useLocation()
  const [analysis, setAnalysis] = useState(location.state?.analysis ?? null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (analysis) return undefined

    const controller = new AbortController()

    getAnalysis(analysisId, { signal: controller.signal })
      .then(setAnalysis)
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') setError(requestError.message)
      })

    return () => controller.abort()
  }, [analysis, analysisId])

  if (error) return <p role="alert">{error}</p>
  if (!analysis) return <p>Loading analysis…</p>
  if (analysis.state === ANALYSIS_STATES.FAILED) {
    return <p role="alert">{analysis.error}</p>
  }
  if (analysis.state !== ANALYSIS_STATES.COMPLETE) {
    return <p>Analysis state: {analysis.state}</p>
  }

  return <pre>{JSON.stringify(analysis.result, null, 2)}</pre>
}
```

This example fetches one status snapshot after refresh. If a refreshed Results page should continue waiting, call `pollAnalysis` instead of `getAnalysis`.

## 8. CORS and local development

The deployed stack currently allows exactly:

```text
http://localhost:5173
```

API Gateway permits browser requests from that origin using `GET`, `POST`, and `OPTIONS`, with `Content-Type` as the allowed request header. The S3 bucket permits `PUT` and `HEAD` from the same origin, allows `Content-Type` and `x-amz-server-side-encryption`, and exposes `ETag`.

Origins include scheme, hostname, and port. These are different origins and are not currently allowed:

- `http://127.0.0.1:5173`
- `http://localhost:3000`
- `https://localhost:5173`
- Any deployed frontend domain

For a production frontend, the backend stack must be updated with that exact production origin. Changing a frontend environment variable does not change backend CORS.

When troubleshooting CORS:

1. Confirm Vite is actually using `http://localhost:5173`.
2. Inspect the browser Network panel and identify whether API Gateway or S3 rejected the request.
3. Confirm the S3 upload uses only the exact returned method and signed headers.
4. Confirm the browser did not send `multipart/form-data` or omit the encryption header.
5. Confirm the presigned URL has not expired.
6. Do not disable browser security as a workaround.

## 9. Gemini AI insights

Gemini is optional and is currently disabled in the deployed stack because no Gemini Secrets Manager ARN was supplied during deployment. The matching pipeline still works normally.

The frontend should treat this as an expected value:

```json
{
  "status": "unavailable",
  "insight": null,
  "model": null
}
```

Recommended behavior:

- Render the deterministic match, timestamps, transcript context, and similarity normally.
- Hide or disable the AI-insight section when `status` is `unavailable`.
- Do not label the entire analysis as failed.
- Treat an empty `context_flags` array as a valid result.
- Never send a Gemini API key from the frontend. If enabled later, the worker reads it server-side from AWS Secrets Manager.

## 10. Troubleshooting

### Invalid video format

The create endpoint accepts only filenames ending in `.mp4` and the exact content type `video/mp4`. The frontend service validates the filename before creating the record. A valid extension does not guarantee valid media; FFmpeg can still return a result-level `ERROR` later.

### S3 upload fails

- Use `PUT`, not `POST`.
- Send the `File` directly, not `FormData`.
- Use the exact `headers` object from the upload instruction.
- Do not attach cookies, AWS credentials, or an application authorization header.
- Verify the URL is less than 15 minutes old.
- Verify the browser origin is allowed.
- If one upload fails, do not call completion.

### HTTP 400

For create requests, inspect file descriptors, JSON syntax, `use_ai`, filenames, and content type. For completion, an uploaded file may be empty, too large, or have incorrect S3 metadata.

### HTTP 404

The analysis ID is unknown, malformed at the routing level, or its two-day record has already expired. Do not silently create a replacement unless the user chooses to retry.

### HTTP 409

Completion ran before both S3 objects were visible. Confirm both upload requests returned a 2xx response, then retry completion once.

### HTTP 500

The backend encountered an unexpected operational error. Show a retry option and retain a diagnostic-safe message, but do not expose internal details to the user.

### Analysis remains `QUEUED`

The worker may be busy, concurrency-limited, retrying, or waiting for SQS delivery. Continue bounded polling. The deployed SQS event source permits at most two concurrent worker invocations.

### Analysis remains `PROCESSING`

CPU transcription can take several minutes. The worker timeout is 900 seconds. A browser timeout does not cancel the Lambda. Allow a later status refresh before starting another analysis.

### Polling timeout

Catch `PollingTimeoutError`, stop automatic polling, and offer “Check again” rather than automatically submitting the videos again.

### Missing match or context fields

Check `result.status` first. `match` and `context` are guaranteed only for `MATCH_FOUND`; they are intentionally null for `NO_MATCH`, `AMBIGUOUS_MATCH`, and `ERROR`.

### CORS error

Use the exact allowed origin and distinguish API Gateway CORS from S3 CORS in the Network panel. A CORS error can also hide an S3 signature error caused by missing or changed signed headers.

### Expired presigned URL

Presigned URLs expire after 900 seconds. There is no refresh endpoint. Create a new analysis only after telling the user that the previous upload session expired.

## 11. Security and operational notes

- Never put AWS access keys, Gemini keys, secret ARNs, or other credentials in frontend source, Vite variables, browser storage, or requests.
- Treat presigned URLs as temporary sensitive values. Avoid analytics capture, console logging, error-reporting payloads, and persistent storage of the URL.
- The deployed API currently has no authentication. Anyone who knows the API URL can call it.
- CORS controls which browser origins may read/send supported browser requests; it is not authentication and does not stop scripts or direct HTTP clients.
- API Gateway is configured for a steady rate of 5 requests per second with a burst of 10. Excess traffic can receive HTTP 429.
- Worker concurrency is capped at two, but this is not an account-wide spending cap.
- The worker uses 3,008 MB of Lambda memory and can run for up to 15 minutes, so unnecessary analyses have a real cost.
- Avoid excessive polling, duplicate completion requests, automatic resubmission, and repeated processing.
- S3 uploads expire after two days; DynamoDB records have a two-day TTL; CloudWatch logs are retained for seven days.
- Failed SQS messages are retried according to the worker/queue configuration and move to the dead-letter queue after the configured receive count.
- AWS budget alerts notify about spending; they do not automatically stop resources or enforce a hard cap.
- Never present similarity as a factual truth or misinformation score. It measures transcript matching, while context flags describe transcript-supported contextual differences.

## 12. Quick-start checklist

- [ ] Run the frontend at exactly `http://localhost:5173`.
- [ ] Set `VITE_CONTEXTLENS_API_URL` or use the deployed default.
- [ ] Import the functions from `frontend/src/services/api.js`.
- [ ] Collect one original MP4 `File` and one shorter MP4 `File`.
- [ ] Call `createAnalysis({ original, clip, useAi })`.
- [ ] Keep the returned `analysis_id`.
- [ ] Pass both files and `created.uploads` to `uploadAnalysisVideos`.
- [ ] Wait for both uploads to succeed.
- [ ] Call `completeAnalysis(created.analysis_id)` exactly once.
- [ ] Poll with `pollAnalysis` and display `onUpdate` states.
- [ ] Stop on top-level `COMPLETE` or `FAILED`.
- [ ] For `COMPLETE`, branch on `result.status` before reading `match` or `context`.
- [ ] Handle unavailable AI insights and empty context flags gracefully.
- [ ] Support cancellation with one shared `AbortController`.
- [ ] Never log or persist presigned URLs, AWS credentials, or secrets.
- [ ] Test page refresh behavior by loading results from the route's analysis ID.
- [ ] Before production, update backend CORS to the exact deployed frontend origin.
