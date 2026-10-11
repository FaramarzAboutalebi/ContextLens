# ContextLens Fact-Check Frontend Integration

This API belongs to the independent `contextlens-factcheck-dev` stack. It is separate from the existing `/analyses` API and does not change the two-video comparison workflow.

## Base URL

Development stack base URL:

```text
https://njd695aq33.execute-api.us-east-1.amazonaws.com
```

For other environments, read the URL from the `ApiBaseUrl` CloudFormation output.

All requests and responses use JSON except the direct S3 form upload.

## Job states

- `UPLOADING`: waiting for a manual MP4 upload and completion request
- `QUEUED`: accepted and waiting for the worker
- `PROCESSING`: download/transcription/review in progress
- `COMPLETED`: terminal success; inspect `result`
- `FAILED`: terminal failure; inspect `error.code` and `error.message`

Poll every 3–5 seconds while a job is `QUEUED` or `PROCESSING`. Stop on `COMPLETED` or `FAILED`. Do not poll faster than once every two seconds.

## Instagram URL mode

Request:

```http
POST /fact-checks
Content-Type: application/json
```

```json
{
  "source": {
    "type": "instagram_url",
    "url": "https://www.instagram.com/reel/DePHLhtON_i/"
  }
}
```

Accepted response (`202`):

```json
{
  "fact_check_id": "uuid",
  "status": "QUEUED"
}
```

Only authorized, public, HTTPS Reel URLs are accepted. Query parameters are discarded during normalization. If Instagram blocks retrieval, show the returned failure and offer manual upload as a new job.

## Manual MP4 mode

Create the job:

```json
{
  "source": {
    "type": "manual_upload",
    "filename": "authorized-video.mp4",
    "content_type": "video/mp4"
  }
}
```

The `201` response contains a short-lived S3 POST form:

```json
{
  "fact_check_id": "uuid",
  "status": "UPLOADING",
  "upload": {
    "url": "signed S3 URL",
    "method": "POST",
    "fields": {
      "key": "signed value",
      "policy": "signed value"
    }
  },
  "expires_in": 900
}
```

Do not log or persist the URL or fields. Construct `FormData`, append every returned field first, then append the file using the field name `file`:

```js
async function uploadManualVideo(upload, file) {
  const form = new FormData();
  for (const [name, value] of Object.entries(upload.fields)) {
    form.append(name, value);
  }
  form.append("file", file);

  const response = await fetch(upload.url, {
    method: "POST",
    body: form,
  });
  if (!response.ok) throw new Error("Video upload failed");
}
```

S3 enforces a 1-byte-to-75-MB policy. The worker independently validates the real streams and 180-second duration.

After a successful upload:

```http
POST /fact-checks/{fact_check_id}/complete
Content-Type: application/json
```

Body: `{}`

The response is `202` with the current state. Repeating completion is safe and does not queue duplicate processing.

## Poll a job

```http
GET /fact-checks/{fact_check_id}
```

Nonterminal response:

```json
{
  "fact_check_id": "uuid",
  "status": "PROCESSING",
  "schema_version": "1.0",
  "result": null,
  "error": null
}
```

Completed response:

```json
{
  "fact_check_id": "uuid",
  "status": "COMPLETED",
  "schema_version": "1.0",
  "result": {
    "fact_check_id": "uuid",
    "status": "COMPLETED",
    "schema_version": "1.0",
    "source": {
      "type": "instagram_url",
      "url": "https://www.instagram.com/reel/example/",
      "duration_seconds": 65.5
    },
    "transcript": {
      "text": "Full transcript",
      "segments": [
        {"start": 0.0, "end": 4.2, "text": "Spoken text"}
      ],
      "duration_seconds": 65.5
    },
    "review": {
      "status": "SUCCESS",
      "model": "gemini-3.8-flash",
      "summary": {
        "verdict": "MIXED",
        "explanation": "Reviewed 4 of 6 identified factual claims: 2 supported, 1 contradicted, 1 mixed, and 0 with insufficient evidence. Key concerns: “Claim as spoken” was contradicted. Partial review: 2 identified factual claims were omitted because of the review limit.",
        "factual_claims_identified": 6,
        "factual_claims_reviewed": 4,
        "factual_claims_omitted": 2,
        "assessment_counts": {
          "supported": 2,
          "contradicted": 1,
          "mixed": 1,
          "insufficient_evidence": 0
        },
        "content_item_counts": {
          "prediction": 1,
          "opinion": 0,
          "financial_advice": 1,
          "guaranteed_return": 0
        },
        "partial_review": true,
        "coverage_warning": "Partial review: 2 identified factual claims were omitted because of the review limit.",
        "key_findings": [
          {
            "claim_id": "claim-2",
            "assessment": "CONTRADICTED",
            "text": "Claim as spoken"
          }
        ]
      },
      "claims": [
        {
          "claim_id": "claim-1",
          "text": "Claim as spoken",
          "timestamp_seconds": 12.4,
          "excerpt": "Supporting transcript excerpt",
          "context_excerpt": "Surrounding transcript before and after the exact quote.",
          "importance": "HIGH",
          "risk_tags": ["CENTRAL_ARGUMENT", "TAX_OR_LEGAL"],
          "assessment": "SUPPORTED",
          "claim_fidelity": "PRESERVED",
          "fidelity_explanation": "The normalized claim preserves the original assertion.",
          "explanation": "Evidence-based explanation",
          "sources": [
            {
              "title": "Source title",
              "url": "https://source.example/article",
              "authority": "PRIMARY",
              "evidence_excerpt": "The source passage directly used for this assessment."
            }
          ],
          "limitations": []
        }
      ],
      "unreviewed_claims": [
        {
          "claim_id": "claim-5",
          "text": "An identified claim not reviewed because of the configured limit.",
          "timestamp_seconds": 42.1,
          "excerpt": "Exact transcript evidence."
        }
      ],
      "content_items": [
        {
          "item_id": "item-1",
          "type": "PREDICTION",
          "text": "A future-looking statement.",
          "timestamp_seconds": 24.0,
          "excerpt": "Exact transcript evidence."
        },
        {
          "item_id": "item-2",
          "type": "FINANCIAL_ADVICE",
          "text": "A recommendation made by the speaker.",
          "timestamp_seconds": 31.0,
          "excerpt": "Exact transcript evidence."
        }
      ]
    },
    "error": null
  },
  "error": null
}
```

`review.status` can be:

- `SUCCESS`: review completed
- `NO_CHECKABLE_CLAIMS`: transcription succeeded, but no suitable claims were found
- `UNAVAILABLE`: transcript may be present, but Gemini extraction or grounding was unavailable

Assessment meanings:

- `SUPPORTED`: retrieved evidence supports the claim
- `CONTRADICTED`: retrieved evidence directly conflicts with the claim
- `MIXED`: credible evidence supports and conflicts with material parts
- `INSUFFICIENT_EVIDENCE`: evidence is absent, weak, or grounding citations were unavailable

## Overall summary and statement types

`review.summary` is computed deterministically from claim-level results; Gemini does not invent the
overall verdict. Display it above the claim list. Supported verdicts are:

- `MOSTLY_SUPPORTED`
- `MIXED`
- `MOSTLY_MISLEADING`
- `INSUFFICIENT_EVIDENCE`

The aggregation rule is intentionally conservative:

1. If fewer than half of reviewed claims have adequate evidence, the verdict is
   `INSUFFICIENT_EVIDENCE`.
2. Otherwise, a majority of contradicted conclusive claims produces `MOSTLY_MISLEADING`.
3. At least two-thirds supported conclusive claims, with more support than contradiction, produces
   `MOSTLY_SUPPORTED`.
4. All other combinations produce `MIXED`.

Never convert counts into a fictional accuracy percentage. Present wording such as “4 of 6 reviewed
claims were supported.” When `partial_review` is `true`, prominently show `coverage_warning`.

`review.claims` remains the backward-compatible reviewed-claim array. New fields are additive:

- `summary`: video-level verdict, counts, coverage warning, and up to three `key_findings`
- `unreviewed_claims`: identified factual claims omitted by the review budget
- `content_items`: important non-factual or advisory statements

Each reviewed claim preserves `excerpt` plus a wider `context_excerpt`. `importance` and
`risk_tags` explain why a claim was selected. `claim_fidelity` is `PRESERVED`, `PARTIAL`, or
`MISMATCHED`; a `SUPPORTED` result is downgraded when the normalized claim does not faithfully
represent the video's assertion. Display `fidelity_explanation` and `limitations` for `MIXED` or
uncertain results.

`content_items[].type` is one of:

- `PREDICTION`: a future-looking statement; do not display it as false solely because it is future
- `OPINION`: subjective or value-based language
- `FINANCIAL_ADVICE`: a recommendation or call to action
- `GUARANTEED_RETURN`: an absolute or unrealistic certainty claim requiring prominent warning UI

Each accepted source now includes `authority` (`PRIMARY` or `SECONDARY`) and the grounded
`evidence_excerpt` used to establish relevance. The backend rejects uncited grounding chunks and
known low-quality social sources. The browser must still treat all source text as untrusted data.

The worker reviews six factual claims by default, configurable at deployment from one through the
hard maximum of eight. It prioritizes central, high-harm financial/legal, guaranteed-return,
tax, numerical, and regulatory claims rather than simply reviewing the first six. If more are
identified, the response explicitly reports what was omitted.

## Creation rate limits

Only `POST /fact-checks` consumes creation quota. Polling and the idempotent manual-upload
completion route do not create or charge another job. The development stack defaults to:

- 6 new jobs per source-IP hash per UTC hour
- 30 new jobs across the API per UTC hour
- 100 new jobs across the API per UTC day

When a limit is reached, the API returns HTTP `429`:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Fact-check creation limit reached. Please try again later."
  }
}
```

Read the `Retry-After` response header and disable new submissions until that many seconds have
passed. Existing jobs remain pollable. The server hashes the API Gateway source IP and never stores
the raw address. These fixed-window limits bound paid job creation for a controlled demo; they are
not authentication or a guaranteed AWS spending cap. Users behind one NAT may share a limit.

## Failure handling

A failed polling response has a safe machine-readable error:

```json
{
  "fact_check_id": "uuid",
  "status": "FAILED",
  "schema_version": "1.0",
  "result": null,
  "error": {
    "code": "INSTAGRAM_DOWNLOAD_FAILED",
    "message": "Instagram could not provide this public Reel. Upload an authorized MP4 instead."
  }
}
```

Expected error codes include:

- `RATE_LIMITED` (creation response only, HTTP `429`; honor `Retry-After`)
- `INVALID_INSTAGRAM_URL`
- `INSTAGRAM_DOWNLOAD_FAILED`
- `VIDEO_TOO_LARGE`
- `VIDEO_TOO_LONG`
- `UNSUPPORTED_MEDIA`
- `NO_AUDIO`
- `NO_SPEECH`
- `TRANSCRIPTION_FAILED`
- `GROUNDING_UNAVAILABLE`
- `PROCESSING_FAILED`

For `INSTAGRAM_DOWNLOAD_FAILED`, guide the user to manual upload. Never show presigned S3 details after the upload step, and never send Gemini credentials from the browser.

## Polling helper

```js
export async function waitForFactCheck(apiBaseUrl, factCheckId, options = {}) {
  const intervalMs = options.intervalMs ?? 4000;
  const timeoutMs = options.timeoutMs ?? 15 * 60 * 1000;
  const started = Date.now();

  while (Date.now() - started < timeoutMs) {
    const response = await fetch(
      `${apiBaseUrl}/fact-checks/${encodeURIComponent(factCheckId)}`,
    );
    if (!response.ok) throw new Error("Fact-check status request failed");
    const job = await response.json();
    if (job.status === "COMPLETED" || job.status === "FAILED") return job;
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error("Fact-check processing timed out");
}
```

The browser origin must exactly match either `FrontendOrigin` (local development) or
`ProductionFrontendOrigin`. S3 upload CORS and API Gateway CORS use the same explicit origin list.
