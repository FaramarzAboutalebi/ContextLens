const DEFAULT_FACTCHECK_API_BASE_URL =
  'https://njd695aq33.execute-api.us-east-1.amazonaws.com'

export const FACTCHECK_API_BASE_URL = (
  import.meta.env?.VITE_CONTEXTLENS_FACTCHECK_API_URL ||
  DEFAULT_FACTCHECK_API_BASE_URL
).replace(/\/$/, '')

export const FACT_CHECK_STATES = Object.freeze({
  CREATED: 'CREATED',
  UPLOADING: 'UPLOADING',
  QUEUED: 'QUEUED',
  PROCESSING: 'PROCESSING',
  COMPLETED: 'COMPLETED',
  FAILED: 'FAILED',
})

const TERMINAL_STATES = new Set([
  FACT_CHECK_STATES.COMPLETED,
  FACT_CHECK_STATES.FAILED,
])

const KNOWN_STATES = new Set(Object.values(FACT_CHECK_STATES))

export class FactCheckApiError extends Error {
  constructor(message, { status = 0, code = null, retryAfter = null } = {}) {
    super(message)
    this.name = 'FactCheckApiError'
    this.status = status
    this.code = code
    this.retryAfter = retryAfter
  }
}

async function readResponse(response) {
  const text = await response.text()
  let body = null

  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = { error: { message: text } }
    }
  }

  if (!response.ok) {
    const error = body?.error
    const message =
      (typeof error === 'object' ? error?.message : error) ||
      body?.message ||
      `Request failed with HTTP ${response.status}.`

    throw new FactCheckApiError(message, {
      status: response.status,
      code: typeof error === 'object' ? error?.code : null,
      retryAfter: response.headers.get('Retry-After'),
    })
  }

  return body
}

function requireFactCheckId(factCheckId) {
  if (typeof factCheckId !== 'string' || !factCheckId.trim()) {
    throw new TypeError('factCheckId must be a non-empty string.')
  }
  return encodeURIComponent(factCheckId.trim())
}

export function normalizeInstagramReelUrl(value) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new TypeError('Enter an Instagram Reel URL.')
  }

  let url
  try {
    url = new URL(value.trim())
  } catch {
    throw new TypeError('Enter a valid Instagram Reel URL.')
  }

  const hostname = url.hostname.toLowerCase()
  const parts = url.pathname.split('/').filter(Boolean)
  const shortcode = parts[1] || ''

  if (
    url.protocol !== 'https:' ||
    !['instagram.com', 'www.instagram.com'].includes(hostname) ||
    parts.length !== 2 ||
    parts[0].toLowerCase() !== 'reel' ||
    !/^[A-Za-z0-9_-]{5,64}$/.test(shortcode)
  ) {
    throw new TypeError(
      'Use a public URL in the format https://www.instagram.com/reel/…/',
    )
  }

  return `https://www.instagram.com/reel/${shortcode}/`
}

export async function createInstagramFactCheck(instagramUrl, { signal } = {}) {
  const normalizedUrl = normalizeInstagramReelUrl(instagramUrl)
  const response = await fetch(`${FACTCHECK_API_BASE_URL}/fact-checks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source: {
        type: 'instagram_url',
        url: normalizedUrl,
      },
    }),
    signal,
  })

  return readResponse(response)
}

export async function getFactCheck(factCheckId, { signal } = {}) {
  const response = await fetch(
    `${FACTCHECK_API_BASE_URL}/fact-checks/${requireFactCheckId(factCheckId)}`,
    { signal },
  )

  return readResponse(response)
}

function abortableDelay(milliseconds, signal) {
  if (signal?.aborted) {
    return Promise.reject(signal.reason || new DOMException('Aborted', 'AbortError'))
  }

  return new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer)
      reject(signal.reason || new DOMException('Aborted', 'AbortError'))
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve()
    }, milliseconds)

    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

export async function pollFactCheck(
  factCheckId,
  {
    intervalMs = 4_000,
    timeoutMs = 15 * 60 * 1_000,
    signal,
    onUpdate,
  } = {},
) {
  if (!Number.isFinite(intervalMs) || intervalMs < 2_000) {
    throw new TypeError('intervalMs must be at least 2000 milliseconds.')
  }
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new TypeError('timeoutMs must be greater than zero.')
  }

  const deadline = Date.now() + timeoutMs

  while (true) {
    const job = await getFactCheck(factCheckId, { signal })

    if (!KNOWN_STATES.has(job.status)) {
      throw new FactCheckApiError(
        `Backend returned unknown fact-check status: ${job.status}.`,
      )
    }

    onUpdate?.(job)

    if (TERMINAL_STATES.has(job.status)) {
      return job
    }
    if (Date.now() >= deadline) {
      throw new FactCheckApiError(
        'Fact-check processing did not finish within 15 minutes.',
      )
    }

    await abortableDelay(Math.min(intervalMs, deadline - Date.now()), signal)
  }
}
