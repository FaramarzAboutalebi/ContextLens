import { Link, useParams, useLocation } from 'react-router-dom';
import { useEffect, useState } from 'react';
import VideoPlayer from '../components/VideoPlayer';
import { Button } from '@mui/material';
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

    const [videoUrls, setVideoUrls] = useState({
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

        setVideoUrls({
            shortClip: shortClipUrl,
            originalVideo: originalVideoUrl,
        });

        return () => {
            if (shortClipUrl) URL.revokeObjectURL(shortClipUrl);
            if (originalVideoUrl) URL.revokeObjectURL(originalVideoUrl);
        };
    }, [location.state]);


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
            <h1>Your video analysis</h1>
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
                        />

                        <VideoPlayer
                            title="Original Video"
                            src={videoUrls.originalVideo}
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

            {!location.state?.shortClip && !location.state?.originalVideo && (
                <p className="demo-label" role="status">
                    Uploaded videos are available only during the current analysis session.
                    Return to Analyze to upload them again.
                </p>
            )}
        </div>
        </main>
    );
}

export default Results;