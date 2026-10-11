import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { Alert, Button } from '@mui/material';
import {
    FACT_CHECK_STATES,
    getFactCheck,
    pollFactCheck,
} from '../services/factcheckApi';

const VERDICT_LABELS = {
    MOSTLY_SUPPORTED: 'Mostly supported',
    MIXED: 'Mixed evidence',
    MOSTLY_MISLEADING: 'Mostly misleading',
    INSUFFICIENT_EVIDENCE: 'Insufficient evidence',
};

const ASSESSMENT_LABELS = {
    SUPPORTED: 'Supported',
    CONTRADICTED: 'Contradicted',
    MIXED: 'Mixed',
    INSUFFICIENT_EVIDENCE: 'Insufficient evidence',
};

const CONTENT_ITEM_LABELS = {
    PREDICTION: 'Predictions',
    OPINION: 'Opinions',
    FINANCIAL_ADVICE: 'Financial advice',
    GUARANTEED_RETURN: 'Guaranteed-return statements',
};

const STATUS_COPY = {
    CREATED: ['Starting your review…', 'The fact-check job is being prepared.'],
    UPLOADING: ['Waiting for the video…', 'The video upload must finish before analysis can begin.'],
    QUEUED: ['Your review is queued…', 'ContextLens will begin processing as soon as a worker is available.'],
    PROCESSING: ['Reviewing the Reel…', 'ContextLens is transcribing the audio and checking factual claims.'],
};

const RECOGNIZABLE_SOURCES = {
    'irs.gov': 'IRS',
    'www.irs.gov': 'IRS',
    'sec.gov': 'U.S. SEC',
    'www.sec.gov': 'U.S. SEC',
    'consumerfinance.gov': 'CFPB',
    'www.consumerfinance.gov': 'CFPB',
    'fidelity.com': 'Fidelity',
    'www.fidelity.com': 'Fidelity',
};

function formatTimestamp(seconds) {
    if (typeof seconds !== 'number' || !Number.isFinite(seconds)) return '—';
    const minutes = Math.floor(seconds / 60);
    const remaining = Math.floor(seconds % 60);
    return `${String(minutes).padStart(2, '0')}:${String(remaining).padStart(2, '0')}`;
}

function compactText(value, maxLength = 220) {
    if (typeof value !== 'string') return '';
    const text = value.trim();
    if (text.length <= maxLength) return text;

    const clipped = text.slice(0, maxLength);
    const sentenceEnd = Math.max(
        clipped.lastIndexOf('. '),
        clipped.lastIndexOf('? '),
        clipped.lastIndexOf('! '),
    );
    const end = sentenceEnd >= 90 ? sentenceEnd + 1 : clipped.lastIndexOf(' ');
    return `${clipped.slice(0, Math.max(end, 1)).trim()}…`;
}

function safeExternalUrl(value) {
    try {
        const url = new URL(value);
        return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
    } catch {
        return null;
    }
}

function sourceDisplayName(source) {
    const title = typeof source?.title === 'string' ? source.title.trim() : '';
    const normalizedTitle = title.toLowerCase().replace(/^www\./, '');
    if (RECOGNIZABLE_SOURCES[normalizedTitle]) {
        return RECOGNIZABLE_SOURCES[normalizedTitle];
    }

    const citationUrl = safeExternalUrl(source?.url);
    if (citationUrl) {
        const hostname = new URL(citationUrl).hostname.toLowerCase();
        if (RECOGNIZABLE_SOURCES[hostname]) {
            return RECOGNIZABLE_SOURCES[hostname];
        }
    }

    return title || (citationUrl ? new URL(citationUrl).hostname.replace(/^www\./, '') : 'Evidence source');
}

function Timestamp({ seconds }) {
    return <time className="claim-time">{formatTimestamp(seconds)}</time>;
}

function ClaimCard({ claim, index }) {
    const assessment = claim.assessment || 'INSUFFICIENT_EVIDENCE';
    const sources = Array.isArray(claim.sources) ? claim.sources : [];
    const limitations = Array.isArray(claim.limitations) ? claim.limitations : [];
    const riskTags = Array.isArray(claim.risk_tags) ? claim.risk_tags : [];
    const explanation = typeof claim.explanation === 'string' ? claim.explanation : '';
    const conciseExplanation = compactText(explanation);
    const citationLabel = `${sources.length} citation${sources.length === 1 ? '' : 's'}`;

    return (
        <article className="claim-card">
            <div className="claim-card-head">
                <Timestamp seconds={claim.timestamp_seconds} />
                <span className={`assessment-badge assessment-${assessment.toLowerCase()}`}>
                    {ASSESSMENT_LABELS[assessment] || assessment}
                </span>
            </div>

            <h3>{claim.text || 'Claim text unavailable'}</h3>
            <p className="claim-compact-explanation">
                {conciseExplanation || 'No explanation was returned for this claim.'}
            </p>

            <details className="claim-evidence" open={index === 0}>
                <summary>
                    <span>View evidence</span>
                    <span className="citation-count">{citationLabel}</span>
                </summary>

                <div className="claim-evidence-body">
                    {(claim.importance || riskTags.length > 0) && (
                        <div className="claim-tags" aria-label="Claim priority and risk tags">
                            {claim.importance && <span>{claim.importance} importance</span>}
                            {riskTags.map((tag) => (
                                <span key={tag}>{tag.replaceAll('_', ' ')}</span>
                            ))}
                        </div>
                    )}

                    {explanation && (
                        <div className="evidence-block">
                            <h4>Full explanation</h4>
                            <p>{explanation}</p>
                        </div>
                    )}

                    {claim.excerpt && (
                        <div className="evidence-block">
                            <h4>Original transcript quote</h4>
                            <blockquote>“{claim.excerpt}”</blockquote>
                        </div>
                    )}

                    {claim.context_excerpt && claim.context_excerpt !== claim.excerpt && (
                        <div className="evidence-block">
                            <h4>Surrounding transcript</h4>
                            <p className="surrounding-context">{claim.context_excerpt}</p>
                        </div>
                    )}

                    {claim.claim_fidelity && claim.claim_fidelity !== 'PRESERVED' && (
                        <Alert severity="warning" className="fidelity-warning">
                            <strong>{claim.claim_fidelity} claim fidelity.</strong>{' '}
                            {claim.fidelity_explanation || 'The normalized claim may not fully preserve the original wording.'}
                        </Alert>
                    )}

                    <div className="claim-sources">
                        <h4>Sources</h4>
                        {sources.length === 0 ? (
                            <Alert severity="info">
                                No supporting citations were returned for this assessment.
                            </Alert>
                        ) : (
                            sources.map((source, sourceIndex) => {
                                const citationUrl = safeExternalUrl(source.url);
                                return (
                                    <article className="citation" key={`${source.url || source.title}-${sourceIndex}`}>
                                        <div className="citation-heading">
                                            {citationUrl ? (
                                                <a href={citationUrl} target="_blank" rel="noreferrer">
                                                    {sourceDisplayName(source)} ↗
                                                </a>
                                            ) : (
                                                <strong>{sourceDisplayName(source)}</strong>
                                            )}
                                            {source.authority && (
                                                <span>{source.authority}</span>
                                            )}
                                        </div>
                                        {source.evidence_excerpt && (
                                            <p>{source.evidence_excerpt}</p>
                                        )}
                                    </article>
                                );
                            })
                        )}
                    </div>

                    {limitations.length > 0 && (
                        <div className="claim-limitations">
                            <strong>Limitations and warnings</strong>
                            <ul>
                                {limitations.map((limitation, limitationIndex) => (
                                    <li key={`${limitation}-${limitationIndex}`}>{limitation}</li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            </details>
        </article>
    );
}

function FactCheckResults() {
    const { factCheckId } = useParams();
    const location = useLocation();
    const [job, setJob] = useState(location.state?.factCheck ?? null);
    const [shareMessage, setShareMessage] = useState('');

    const shareResult = async () => {
        const shareUrl = `${window.location.origin}/fact-check-results/${encodeURIComponent(factCheckId)}`;

        try {
            await navigator.clipboard.writeText(shareUrl);
            setShareMessage('Link copied!');
        } catch {
            setShareMessage('Could not copy the link. Please copy the URL from your address bar.');
        }
    };
    const [loadError, setLoadError] = useState('');

    useEffect(() => {
        const controller = new AbortController();

        async function loadFactCheck() {
            try {
                const current = await getFactCheck(factCheckId, {
                    signal: controller.signal,
                });
                if (controller.signal.aborted) return;
                setJob(current);

                if (
                    current.status === FACT_CHECK_STATES.COMPLETED ||
                    current.status === FACT_CHECK_STATES.FAILED
                ) {
                    return;
                }

                const finished = await pollFactCheck(factCheckId, {
                    intervalMs: 4000,
                    timeoutMs: 15 * 60 * 1000,
                    signal: controller.signal,
                    onUpdate: (updated) => {
                        if (!controller.signal.aborted) setJob(updated);
                    },
                });
                if (!controller.signal.aborted) setJob(finished);
            } catch (error) {
                if (!controller.signal.aborted) {
                    setLoadError(error.message || 'Unable to retrieve this fact-check.');
                }
            }
        }

        loadFactCheck();
        return () => controller.abort();
    }, [factCheckId]);

    if (loadError) {
        return (
            <main className="results-page">
                <div className="results-container">
                    <p className="eyebrow">FACT-CHECK RESULTS</p>
                    <h1>Result unavailable</h1>
                    <Alert severity="error">{loadError}</Alert>
                    <Button
                        component={Link}
                        to="/analyze?mode=instagram"
                        className="button fact-check-back-button"
                    >
                        Try another Reel →
                    </Button>
                </div>
            </main>
        );
    }

    if (!job || ![FACT_CHECK_STATES.COMPLETED, FACT_CHECK_STATES.FAILED].includes(job.status)) {
        const [heading, description] = STATUS_COPY[job?.status] || STATUS_COPY.CREATED;
        return (
            <main className="results-page">
                <div className="results-container fact-check-loading">
                    <p className="eyebrow">FACT-CHECK IN PROGRESS</p>
                    <h1>{heading}</h1>
                    <p className="dialog-copy">
                        {description} This can take several minutes.
                    </p>
                </div>
            </main>
        );
    }

    if (job.status === FACT_CHECK_STATES.FAILED || !job.result) {
        const failure = job.error || {};
        return (
            <main className="results-page">
                <div className="results-container">
                    <p className="eyebrow">FACT-CHECK RESULTS</p>
                    <h1>We couldn’t analyze this Reel</h1>
                    <Alert severity="error">
                        {failure.message || 'Fact-check processing failed. Please try again.'}
                    </Alert>
                    {failure.code === 'INSTAGRAM_DOWNLOAD_FAILED' && (
                        <p className="dialog-copy fact-check-guidance">
                            Instagram did not make this public Reel available to the
                            retrieval worker. Try another public Reel or use the video
                            comparison workflow when you have both files.
                        </p>
                    )}
                    <Button
                        type="button"
                        variant="outlined"
                        onClick={shareResult}
                        sx={{
                            mr: 2,
                            mb: 2,
                            borderColor: '#6036ff',
                            color: '#6036ff',
                            textTransform: 'none',
                            fontWeight: 600,
                        }}
                    >
                        Share Result
                    </Button>

                    <Button
                        component={Link}
                        to="/analyze?mode=instagram"
                        className="button analyze-button"
                    >
                        Analyze Another Reel →
                    </Button>

                    {shareMessage && (
                        <p className="demo-label" role="status" aria-live="polite">
                            {shareMessage}
                        </p>
                    )}

                    <p className="demo-label">Fact-check ID: {factCheckId}</p>
                </div>
            </main>
        );
    }

    const result = job.result;
    const review = result.review || {};
    const summary = review.summary || {};
    const claims = Array.isArray(review.claims) ? review.claims : [];
    const unreviewedClaims = Array.isArray(review.unreviewed_claims)
        ? review.unreviewed_claims
        : [];
    const contentItems = Array.isArray(review.content_items)
        ? review.content_items
        : [];
    const segments = Array.isArray(result.transcript?.segments)
        ? result.transcript.segments
        : [];
    const sourceUrl = safeExternalUrl(result.source?.url);
    const verdict = summary.verdict || 'INSUFFICIENT_EVIDENCE';
    const assessmentCounts = summary.assessment_counts || {};
    const keyConcerns = Array.isArray(summary.key_concerns)
        ? summary.key_concerns
        : Array.isArray(summary.key_findings)
            ? summary.key_findings
            : [];
    const identifiedCount = summary.factual_claims_identified ?? claims.length;
    const reviewedCount = summary.factual_claims_reviewed ?? claims.length;
    const summaryExplanation = typeof summary.explanation === 'string'
        ? summary.explanation
        : 'The review completed without a summary.';
    const compactSummary = compactText(summaryExplanation, 320);

    return (
        <main className="results-page fact-check-results-page">
            <div className="results-container">
                <p className="eyebrow">INSTAGRAM FACT-CHECK</p>

                    <div
                        style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            gap: '16px',
                            flexWrap: 'wrap',
                        }}
                    >
                        <h1>Reel evidence review</h1>

                        <Button
                            type="button"
                            variant="outlined"
                            onClick={shareResult}
                            sx={{
                                borderColor: '#6036ff',
                                color: '#6036ff',
                                textTransform: 'none',
                                fontWeight: 600,
                                whiteSpace: 'nowrap',
                                '&:hover': {
                                    borderColor: '#4c25dd',
                                    backgroundColor: '#f3efff',
                                },
                            }}
                        >
                            Share Result ↗
                        </Button>
                    </div>

                    {shareMessage && (
                        <p className="demo-label" role="status" aria-live="polite">
                            {shareMessage}
                        </p>
                    )}

                    <p className="dialog-copy">
                        Claims are assessed individually against cited evidence—not as an
                        accuracy score for the creator or entire video.
                    </p>

                <section className={`fact-check-summary verdict-${verdict.toLowerCase()}`}>
                    <span className="fact-check-kicker">OVERALL EVIDENCE</span>
                    <h2>{VERDICT_LABELS[verdict] || verdict}</h2>
                    <p className="summary-explanation">{compactSummary}</p>

                    {compactSummary !== summaryExplanation && (
                        <details className="summary-more">
                            <summary>Read full summary</summary>
                            <p>{summaryExplanation}</p>
                        </details>
                    )}

                    <div className="review-coverage">
                        <strong>{reviewedCount} of {identifiedCount}</strong>
                        <span>identified claims reviewed</span>
                    </div>

                    <div className="assessment-counts" aria-label="Claim assessment counts">
                        {Object.entries(ASSESSMENT_LABELS).map(([assessment, label]) => (
                            <div className={`count-${assessment.toLowerCase()}`} key={assessment}>
                                <strong>{assessmentCounts[assessment.toLowerCase()] ?? 0}</strong>
                                <span>{label}</span>
                            </div>
                        ))}
                    </div>

                    {summary.coverage_warning && (
                        <Alert severity="warning" className="coverage-warning">
                            {summary.coverage_warning}
                        </Alert>
                    )}

                    {keyConcerns.length > 0 && (
                        <div className="key-concerns">
                            <h3>Key concerns</h3>
                            <ul>
                                {keyConcerns.slice(0, 3).map((concern, index) => (
                                    <li key={`${concern.claim_id || concern.text || concern}-${index}`}>
                                        {typeof concern === 'string'
                                            ? concern
                                            : concern.text || concern.explanation || 'Important reviewed finding'}
                                        {typeof concern === 'object' && concern.assessment && (
                                            <span>{ASSESSMENT_LABELS[concern.assessment] || concern.assessment}</span>
                                        )}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className="summary-meta">
                        <span>Video length: {formatTimestamp(result.source?.duration_seconds)}</span>
                        {review.model && <span>Model: {review.model}</span>}
                    </div>
                </section>

                {sourceUrl && (
                    <a
                        className="source-reel-link"
                        href={sourceUrl}
                        target="_blank"
                        rel="noreferrer"
                    >
                        View original Reel ↗
                    </a>
                )}

                {review.status === 'UNAVAILABLE' && (
                    <Alert severity="warning" sx={{ mt: 3 }}>
                        The transcript is available, but the evidence review could not be completed.
                    </Alert>
                )}

                {review.status === 'NO_CHECKABLE_CLAIMS' && (
                    <Alert severity="info" sx={{ mt: 3 }}>
                        No suitable factual claims were identified in this Reel.
                    </Alert>
                )}

                {claims.length > 0 && (
                    <section className="fact-check-section claims-section">
                        <div className="fact-check-section-heading">
                            <div>
                                <span className="fact-check-kicker">CLAIM-BY-CLAIM</span>
                                <h2>Evidence review</h2>
                            </div>
                            <span>{claims.length} reviewed</span>
                        </div>

                        <div className="claim-list">
                            {claims.map((claim, index) => (
                                <ClaimCard
                                    claim={claim}
                                    index={index}
                                    key={claim.claim_id || `${claim.text}-${index}`}
                                />
                            ))}
                        </div>
                    </section>
                )}

                {(contentItems.length > 0 || unreviewedClaims.length > 0) && (
                    <section className="fact-check-section secondary-findings">
                        <h2>Additional findings</h2>

                        {Object.entries(CONTENT_ITEM_LABELS).map(([type, label]) => {
                            const items = contentItems.filter((item) => item.type === type);
                            if (items.length === 0) return null;

                            return (
                                <details key={type}>
                                    <summary>{label} ({items.length})</summary>
                                    <div className="detail-list">
                                        {items.map((item, index) => (
                                            <article key={item.item_id || `${type}-${index}`}>
                                                <Timestamp seconds={item.timestamp_seconds} />
                                                <p>{item.text}</p>
                                                {item.excerpt && <blockquote>“{item.excerpt}”</blockquote>}
                                            </article>
                                        ))}
                                    </div>
                                </details>
                            );
                        })}

                        {unreviewedClaims.length > 0 && (
                            <details className="unreviewed-findings">
                                <summary>Identified but not reviewed ({unreviewedClaims.length})</summary>
                                <Alert severity="info">
                                    These statements were identified but were not evidence-reviewed.
                                </Alert>
                                <div className="detail-list">
                                    {unreviewedClaims.map((claim, index) => (
                                        <article key={claim.claim_id || `unreviewed-${index}`}>
                                            <Timestamp seconds={claim.timestamp_seconds} />
                                            <p>{claim.text}</p>
                                            {claim.excerpt && <blockquote>“{claim.excerpt}”</blockquote>}
                                        </article>
                                    ))}
                                </div>
                            </details>
                        )}
                    </section>
                )}

                <section className="fact-check-section transcript-section">
                    <details>
                        <summary>Full transcript ({segments.length} segments)</summary>
                        <div className="transcript-segments">
                            {segments.length > 0 ? (
                                segments.map((segment, index) => (
                                    <p key={`${segment.start}-${index}`}>
                                        <Timestamp seconds={segment.start} />
                                        <span>{segment.text}</span>
                                    </p>
                                ))
                            ) : (
                                <p className="transcript-fallback">
                                    {result.transcript?.text || 'No transcript text was returned.'}
                                </p>
                            )}
                        </div>
                    </details>
                </section>

                <p className="result-disclaimer">
                    ContextLens summarizes retrieved evidence and may be incomplete or wrong.
                    Review the cited sources before making financial, legal, health, or other
                    high-impact decisions.
                </p>

                <Button
                    type="button"
                    variant="outlined"
                    onClick={shareResult}
                    sx={{
                        mr: 2,
                        mb: 2,
                        borderColor: '#6036ff',
                        color: '#6036ff',
                        textTransform: 'none',
                        fontWeight: 600,
                    }}
                >
                    Share Result
                </Button>

                <Button
                    component={Link}
                    to="/analyze?mode=instagram"
                    className="button analyze-button"
                >
                    Analyze Another Reel →
                </Button>

                {shareMessage && (
                    <p className="demo-label" role="status" aria-live="polite">
                        {shareMessage}
                    </p>
                )}

                <p className="demo-label">Fact-check ID: {factCheckId}</p>
            </div>
        </main>
    );
}

export default FactCheckResults;
