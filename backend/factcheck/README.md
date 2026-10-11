# ContextLens Fact-Check Backend

This package is an isolated asynchronous backend for fact-checking public Instagram Reels or manually uploaded MP4 files. It does not share API routes, queues, storage, tables, workers, or result contracts with the existing two-video ContextLens comparison system.

## Architecture

`API Gateway -> API Lambda -> DynamoDB + SQS -> container Lambda -> S3 / FFmpeg / Faster-Whisper / Gemini -> DynamoDB`

The independent SAM template is `template-factcheck.yaml`, and the intended stack name is `contextlens-factcheck-dev`.

## Safety limits

- Public HTTPS URLs matching `instagram.com/reel/{shortcode}` only
- No cookies, Instagram login, proxy rotation, CAPTCHA handling, or retries
- DNS and redirect destinations restricted to public Instagram/Facebook CDN hosts
- 90-second Instagram download deadline
- 75 MB media limit
- 180-second duration limit
- FFprobe stream validation and FFmpeg integrity decoding
- Manual upload size enforced by an S3 presigned POST policy
- Worker SQS maximum concurrency of two
- API Gateway throttle of 2 requests/second with burst 5
- Creation budgets of 6 jobs/source-IP hash/hour, 30 jobs/hour globally, and 100 jobs/day globally
- Six grounded claim reviews per video by default, with a hard maximum of eight
- Up to 16 claims identified so coverage omitted by the review budget remains visible
- Two-day S3 lifecycle and DynamoDB TTL

Automatic Instagram retrieval is best-effort. A failed URL job returns `INSTAGRAM_DOWNLOAD_FAILED`; clients should offer manual upload as a new job.

## Local tests

From the repository root:

```bash
PYTHONPATH=backend python3.12 -m unittest discover -s backend/factcheck/tests -v
PYTHONPATH=backend python3.12 -m unittest discover -s backend/tests -v
sam validate --lint --template-file template-factcheck.yaml \
  --region us-east-1 --profile contextlens
```

Build the x86_64 worker on Apple Silicon:

```bash
DOCKER_HOST="unix://$HOME/.docker/run/docker.sock" \
DOCKER_DEFAULT_PLATFORM=linux/amd64 \
sam build --no-cached --template-file template-factcheck.yaml
```

## Deployment

The deployment user must be authorized for resources prefixed with `contextlens-factcheck-dev`, including the SAM image-repository companion stack. The existing policy was originally restricted to `contextlens-demo*` and must not be broadened beyond the new prefix.

After that permission is added:

```bash
DOCKER_HOST="unix://$HOME/.docker/run/docker.sock" sam deploy \
  --template-file .aws-sam/build/template.yaml \
  --stack-name contextlens-factcheck-dev \
  --region us-east-1 \
  --profile contextlens \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --resolve-image-repos \
  --confirm-changeset \
  --parameter-overrides \
    FrontendOrigin=http://localhost:5173 \
    ProductionFrontendOrigin=https://contextlens-wheat.vercel.app \
    MaxMediaBytes=78643200 \
    MaxVideoSeconds=180 \
    JobTtlSeconds=172800 \
    MaxReviewedClaims=6 \
    RateLimitPerClientHour=6 \
    RateLimitGlobalHour=30 \
    RateLimitGlobalDay=100 \
    GeminiSecretArn=arn:aws:secretsmanager:us-east-1:633398615960:secret:contextlens/gemini-api-key-rXPLY7
```

The worker receives read-only access to that existing secret. The key is never returned by the API or written to logs.

## Result semantics

Claim assessments are `SUPPORTED`, `CONTRADICTED`, `MIXED`, or `INSUFFICIENT_EVIDENCE`. The service does not return fabricated accuracy percentages. Original quotes and surrounding transcript context remain attached to each normalized claim. A narrower supported rule cannot silently turn a broader or absolute video assertion into `SUPPORTED`; fidelity failures produce `MIXED` or `INSUFFICIENT_EVIDENCE`. Only grounding chunks directly cited in Gemini's evidence are eligible, known low-quality social sources are rejected, and a second structured pass selects citations that directly support the assessment. When directly relevant evidence is unavailable, the claim is downgraded to `INSUFFICIENT_EVIDENCE`.

The response adds a deterministic overall summary, omitted-claim coverage warning, unreviewed claim
list, and separately classified predictions, opinions, financial advice, and guaranteed-return
claims. Existing routes, lifecycle states, transcript fields, and `review.claims` remain unchanged.

New-job rate limits use atomic DynamoDB counters in the existing fact-check table. Only the trusted
API Gateway source IP is hashed; the raw address is not stored. `POST /fact-checks` returns HTTP 429
with `RATE_LIMITED` and `Retry-After` when a limit is full. Polling and idempotent completion do not
consume job quota. This is practical demo protection, not user authentication or a guaranteed cost
cap; NAT users share an IP limit and fixed UTC windows can create boundary bursts.

This feature is a review aid. Transcription, claim extraction, and automated evidence synthesis can be wrong and should not be presented as authoritative adjudication.
