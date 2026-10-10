const DEFAULT_API_BASE_URL =
  'https://q21qw3hoc9.execute-api.us-east-1.amazonaws.com'

export const API_BASE_URL = (
  import.meta.env?.VITE_CONTEXTLENS_API_URL || DEFAULT_API_BASE_URL
).replace(/\/$/, '')

export const ANALYSIS_STATES = Object.freeze({
  AWAITING_UPLOADS: 'AWAITING_UPLOADS',
  QUEUED: 'QUEUED',
  PROCESSING: 'PROCESSING',
  COMPLETE: 'COMPLETE',
  FAILED: 'FAILED',
})

export const TERMINAL_ANALYSIS_STATES = new Set([
  ANALYSIS_STATES.COMPLETE,
  ANALYSIS_STATES.FAILED,
])

const KNOWN_ANALYSIS_STATES = new Set(Object.values(ANALYSIS_STATES))
const VIDEO_CONTENT_TYPE = 'video/mp4'

export class ApiError extends Error {
  constructor(message, { status = 0, details = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

export class PollingTimeoutError extends Error {
  constructor(message) {
    super(message)
    this.name = 'PollingTimeoutError'
  }
}

async function readResponse(response) {
  const text = await response.text()
  let body = null

  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = { message: text }
    }
  }

  if (!response.ok) {
    throw new ApiError(
      body?.error || body?.message || `Request failed with HTTP ${response.status}.`,
      { status: response.status, details: body },
    )
  }

  return body
}

function requireAnalysisId(analysisId) {
  if (typeof analysisId !== 'string' || !analysisId.trim()) {
    throw new TypeError('analysisId must be a non-empty string.')
  }
  return encodeURIComponent(analysisId.trim())
}

function videoDescriptor(file, label) {
  if (!file || typeof file.name !== 'string') {
    throw new TypeError(`${label} must be a browser File.`)
  }
  if (!file.name.toLowerCase().endsWith('.mp4')) {
    throw new TypeError(`${label} must be an MP4 file.`)
  }

  return {
    filename: file.name,
    content_type: VIDEO_CONTENT_TYPE,
  }
}

/**
 * Create an analysis record and receive two presigned S3 upload instructions.
 */
export async function createAnalysis(
  { original, clip, useAi = true },
  { signal } = {},
) {
  if (typeof useAi !== 'boolean') {
    throw new TypeError('useAi must be a boolean.')
  }

  const response = await fetch(`${API_BASE_URL}/analyses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      original: videoDescriptor(original, 'original'),
      clip: videoDescriptor(clip, 'clip'),
      use_ai: useAi,
    }),
    signal,
  })

  return readResponse(response)
}

/**
 * Upload one File using the method and signed headers returned by POST /analyses.
 */
export async function uploadVideo(file, upload, { signal } = {}) {
  if (!file) {
    throw new TypeError('file is required.')
  }
  if (!upload?.url || upload.method !== 'PUT' || !upload.headers) {
    throw new TypeError('upload must be a presigned PUT instruction.')
  }

  const response = await fetch(upload.url, {
    method: upload.method,
    headers: upload.headers,
    body: file,
    signal,
  })

  if (!response.ok) {
    const message = await response.text()
    throw new ApiError(
      message || `Video upload failed with HTTP ${response.status}.`,
      { status: response.status },
    )
  }
}

/** Upload the original and clip concurrently using their matching instructions. */
export async function uploadAnalysisVideos(
  { original, clip },
  uploads,
  { signal } = {},
) {
  if (!uploads?.original || !uploads?.clip) {
    throw new TypeError('Both original and clip upload instructions are required.')
  }

  await Promise.all([
    uploadVideo(original, uploads.original, { signal }),
    uploadVideo(clip, uploads.clip, { signal }),
  ])
}

/** Tell the backend that both direct-to-S3 uploads have completed. */
export async function completeAnalysis(analysisId, { signal } = {}) {
  const response = await fetch(
    `${API_BASE_URL}/analyses/${requireAnalysisId(analysisId)}/complete`,
    { method: 'POST', signal },
  )

  return readResponse(response)
}

/** Retrieve the polling envelope: { analysis_id, state, result, error? }. */
export async function getAnalysis(analysisId, { signal } = {}) {
  const response = await fetch(
    `${API_BASE_URL}/analyses/${requireAnalysisId(analysisId)}`,
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

/**
 * Poll until COMPLETE or FAILED. Both terminal envelopes are returned to the caller.
 */
export async function pollAnalysis(
  analysisId,
  {
    intervalMs = 2_000,
    timeoutMs = 15 * 60 * 1_000,
    signal,
    onUpdate,
  } = {},
) {
  if (!Number.isFinite(intervalMs) || intervalMs <= 0) {
    throw new TypeError('intervalMs must be greater than zero.')
  }
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new TypeError('timeoutMs must be greater than zero.')
  }

  const deadline = Date.now() + timeoutMs

  while (true) {
    const analysis = await getAnalysis(analysisId, { signal })

    if (!KNOWN_ANALYSIS_STATES.has(analysis.state)) {
      throw new ApiError(`Backend returned unknown analysis state: ${analysis.state}.`, {
        details: analysis,
      })
    }

    onUpdate?.(analysis)

    if (TERMINAL_ANALYSIS_STATES.has(analysis.state)) {
      return analysis
    }
    if (Date.now() >= deadline) {
      throw new PollingTimeoutError(
        `Analysis did not finish within ${timeoutMs} milliseconds.`,
      )
    }

    await abortableDelay(Math.min(intervalMs, deadline - Date.now()), signal)
  }
}
