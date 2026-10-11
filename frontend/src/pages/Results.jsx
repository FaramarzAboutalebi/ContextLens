import { Link, useParams, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import VideoPlayer from '../components/VideoPlayer';
import { Alert, Button, Snackbar } from '@mui/material';
import {
    ANALYSIS_STATES,
    getAnalysis,
    pollAnalysis,
} from '../services/api';
import TranscriptContext from '../components/TranscriptContext';
import ContextFlags from '../components/ContextFlags';

function Results() {
    const { analysisId } = useParams();
    const location = useLocation();

    const [analysis, setAnalysis] = useState(
        location.state?.analysis ?? null
    );
    const [loadError, setLoadError] = useState('');
    const [shareNotice, setShareNotice] = useState(null);

    const shareResult = async () => {
        const shareUrl = `${window.location.origin}/results/${encodeURIComponent(analysisId)}`;

        try {
            await navigator.clipboard.writeText(shareUrl);
            setShareNotice({
                severity: 'success',
                message: 'Share link copied to your clipboard.',
            });
        } catch {
            setShareNotice({
                severity: 'error',
                message: 'Could not copy the link. Please copy it from your address bar.',
            });
        }
    };

    useEffect(() => {

        const controller = new AbortController();

        async function loadAnalysis() {
            try {
                const current = await getAnalysis(analysisId, {
                    signal: controller.signal,
                });

                if (controller.signal.aborted) return;

                setAnalysis(current);

                if (
                    current.state === ANALYSIS_STATES.COMPLETE ||
                    current.state === ANALYSIS_STATES.FAILED
                ) {
                    return;
                }

                const finished = await pollAnalysis(analysisId, {
                    intervalMs: 2000,
                    timeoutMs: 15 * 60 * 1000,
                    signal: controller.signal,
                    onUpdate: (updated) => {
                        if (!controller.signal.aborted) {
                            setAnalysis(updated);
                        }
                    },
                });

                if (!controller.signal.aborted) {
                    setAnalysis(finished);
                }
            } catch (error) {
                if (!controller.signal.aborted) {
                    setLoadError(
                        error.message || 'Unable to retrieve the analysis.'
                    );
                }
            }
        }

        loadAnalysis();

        return () => controller.abort();
    }, [analysisId]);

    const [localVideoUrls, setLocalVideoUrls] = useState({
        shortClip: null,
        originalVideo: null,
    });

    useEffect(() => {
        const shortClip = location.state?.shortClip;
        const originalVideo = location.state?.originalVideo;

        const shortClipUrl = shortClip
            ? URL.createObjectURL(shortClip)
            : null;

        const originalVideoUrl = originalVideo
            ? URL.createObjectURL(originalVideo)
            : null;

        setLocalVideoUrls({
            shortClip: shortClipUrl,
            originalVideo: originalVideoUrl,
        });

        return () => {
            if (shortClipUrl) URL.revokeObjectURL(shortClipUrl);
            if (originalVideoUrl) URL.revokeObjectURL(originalVideoUrl);
        };
    }, [location.state]);

    const videoUrls = {
        shortClip:
            localVideoUrls.shortClip ?? analysis?.media?.clip?.url ?? null,
        originalVideo:
            localVideoUrls.originalVideo ?? analysis?.media?.original?.url ?? null,
    };
    const videoPosters = {
        shortClip: analysis?.media?.clip?.poster_url ?? null,
        originalVideo: analysis?.media?.original?.poster_url ?? null,
    };


        const apiResult =
            analysis?.state === ANALYSIS_STATES.COMPLETE
                ? analysis.result
                : null;

        const formatTime = (seconds) => {
            if (typeof seconds !== 'number' || !Number.isFinite(seconds)) {
                return '—';
            }

            const minutes = Math.floor(seconds / 60);
            const remainingSeconds = Math.floor(seconds % 60);

            return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
        };

        const result = apiResult
            ? {
                status: apiResult.status,
                similarity: apiResult.similarity,
                start: formatTime(apiResult.match?.start),
                end: formatTime(apiResult.match?.end),
                clipTranscript: apiResult.clip_transcript,
                before: apiResult.context?.before,
                during: apiResult.context?.during,
                after: apiResult.context?.after,
                aiInsights: apiResult.ai_context_insights ?? {
                    status: 'unavailable',
                    insight: null,
                    model: null,
                },
                contextFlags: Array.isArray(apiResult.context_flags)
                    ? apiResult.context_flags
                    : [],
            }
            : null;

    if (!result && !loadError && analysis?.state !== ANALYSIS_STATES.FAILED) {
        if (!analysis) {
            return (
                <main className="results-page">
                    <div className="results-container">
                        <h1>Loading analysis...</h1>
                        <p>Retrieving your analysis from the backend.</p>
                    </div>
                </main>
            );
        }

        if (analysis.state !== ANALYSIS_STATES.FAILED) {
            return (
                <main className="results-page">
                    <div className="results-container">
                        <h1>Analysis status: {analysis.state}</h1>
                        <p>The analysis has not finished yet.</p>
                    </div>
                </main>
            );
        }
    }

    if (!result) {
        return (
            <main className="results-page">
                <div className="results-container">
                    <h1>Analysis unavailable</h1>
                    <p className="dialog-copy" role="alert">
                        {loadError ||
                            analysis?.error ||
                            'We could not load this analysis. Please try again.'}
                    </p>

                    <Button component={Link} to="/analyze" className="button">
                        Try Again →
                    </Button>
                </div>
            </main>
        );
    }

    return (
        <main className="results-page">
        <div className="results-container">
            <p className="eyebrow">ANALYSIS RESULTS</p>

            <div
                style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '16px',
                    flexWrap: 'wrap',
                }}
            >
                <h1>Your video analysis</h1>

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

            <p className="dialog-copy">
                Here's what ContextLens found in the original recording.
            </p>

            <div className="results-panel">
                <ContextFlags status={result.status} />

                {(videoUrls.shortClip || videoUrls.originalVideo) && (
                    <div className="results-videos">
                        <VideoPlayer
                            title="Short Clip"
                            src={videoUrls.shortClip}
                            poster={videoPosters.shortClip}
                        />

                        <VideoPlayer
                            title="Original Video"
                            src={videoUrls.originalVideo}
                            poster={videoPosters.originalVideo}
                        />
                    </div>
                )}

            {result.status === 'MATCH_FOUND' && (
                <>
                    <div className="results-metrics">
                    <div>
                        <span>Text Similarity</span>
                        <strong>{result.similarity}%</strong>
                    </div>
                    <div>
                        <span>Match Start</span>
                        <strong>{result.start}</strong>
                    </div>
                    <div>
                        <span>Match End</span>
                        <strong>{result.end}</strong>
                    </div>
                    </div>

                    <h2>Clip Transcript</h2>
                    <p className="transcript-box">{result.clipTranscript}</p>

                    <TranscriptContext
                    before={result.before}
                    during={result.during}
                    after={result.after}
                    />

                    {result.aiInsights?.status === 'success' &&
                        result.aiInsights.insight && (
                            <section className="ai-insights">
                                <h2>AI Context Insight</h2>

                                <p className="ai-insight-text">
                                    {result.aiInsights.insight}
                                </p>

                                {result.contextFlags.length > 0 && (
                                    <div className="context-flags">
                                        <h3>Context Flags</h3>

                                        {result.contextFlags.map((flag, index) => (
                                            <article
                                                className="context-flag"
                                                key={`${flag.type}-${index}`}
                                            >
                                                <strong>{flag.title}</strong>
                                                <p>{flag.explanation}</p>

                                                {flag.evidence && (
                                                    <blockquote>
                                                        “{flag.evidence}”
                                                    </blockquote>
                                                )}
                                            </article>
                                        ))}
                                    </div>
                                )}
                            </section>
                        )}
                </>
                )}

                {result.status === 'NO_MATCH' && (
                <p className="transcript-box">
                    No reliable matching segment was found. Try uploading a different
                    original video.
                </p>
                )}

                {result.status === 'AMBIGUOUS_MATCH' && (
                <p className="transcript-box">
                    Multiple possible matches were detected. A unique matching segment
                    could not be confirmed.
                </p>
                )}

                {result.status === 'ERROR' && (
                <p className="transcript-box">
                    The analysis could not be completed. Please check your video files
                    and try again.
                </p>
                )}

            <p className="result-disclaimer">
                ContextLens provides surrounding context, not a judgment
                about truthfulness or intent.
            </p>

            <Button
                component={Link}
                to="/analyze"
                className="button analyze-button"
            >
                Analyze Another Video →
            </Button>
            </div>

            <p className="demo-label">
                Analysis ID: {analysisId}
            </p>

            {!videoUrls.shortClip && !videoUrls.originalVideo && (
                <p className="demo-label" role="status">
                    Video playback is no longer available for this analysis.
                </p>
            )}
        </div>

        <Snackbar
            open={Boolean(shareNotice)}
            autoHideDuration={2800}
            onClose={() => setShareNotice(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
        >
            <Alert
                severity={shareNotice?.severity ?? 'success'}
                variant="filled"
                onClose={() => setShareNotice(null)}
                sx={{
                    width: '100%',
                    borderRadius: 3,
                    boxShadow: '0 14px 36px rgba(24, 18, 64, 0.24)',
                    fontWeight: 600,
                }}
            >
                {shareNotice?.message}
            </Alert>
        </Snackbar>
        </main>
    );
}

export default Results;
