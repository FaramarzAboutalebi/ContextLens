import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
    Alert,
    Button,
    CircularProgress,
    TextField,
    ToggleButton,
    ToggleButtonGroup,
} from '@mui/material';
import InstagramIcon from '@mui/icons-material/Instagram';
import VideoLibraryOutlinedIcon from '@mui/icons-material/VideoLibraryOutlined';
import UploadBox from '../components/UploadBox';
import {
    ANALYSIS_STATES,
    createAnalysis,
    uploadAnalysisVideos,
    completeAnalysis,
    pollAnalysis,
} from '../services/api';
import {
    FACT_CHECK_STATES,
    createInstagramFactCheck,
    normalizeInstagramReelUrl,
    pollFactCheck,
} from '../services/factcheckApi';

const VIDEO_LOADING_MESSAGES = [
    'Analyzing your videos...',
    'Looking for matching speech...',
    'Finding the surrounding context...',
    'Still working on your analysis...',
];

const INSTAGRAM_LOADING_MESSAGES = [
    'Retrieving the public Reel...',
    'Transcribing the spoken content...',
    'Identifying factual claims...',
    'Checking claims against external evidence...',
];

function Analyze() {
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const [mode, setMode] = useState(
        searchParams.get('mode') === 'instagram' ? 'instagram' : 'videos'
    );
    const [files, setFiles] = useState([null, null]);
    const [errors, setErrors] = useState(['', '']);
    const [instagramUrl, setInstagramUrl] = useState('');
    const [instagramUrlError, setInstagramUrlError] = useState('');
    const [analyzing, setAnalyzing] = useState(false);
    const [apiError, setApiError] = useState('');
    const [processingStage, setProcessingStage] = useState('');
    const [progressStep, setProgressStep] = useState(0);
    const [messageIndex, setMessageIndex] = useState(0);

    const loadingMessages =
        mode === 'instagram'
            ? INSTAGRAM_LOADING_MESSAGES
            : VIDEO_LOADING_MESSAGES;

    useEffect(() => {
        if (!analyzing || progressStep !== 3) return undefined;

        const interval = window.setInterval(() => {
            setMessageIndex((current) =>
                (current + 1) % loadingMessages.length
            );
        }, 12000);

        return () => window.clearInterval(interval);
    }, [analyzing, progressStep, loadingMessages.length]);

    const changeMode = (_event, nextMode) => {
        if (!nextMode || analyzing) return;
        setMode(nextMode);
        setApiError('');
        setProcessingStage('');
        setProgressStep(0);
    };

    const updateFile = async (index, file) => {
        let error = '';

        if (file) {
            const extension = file.name.split('.').pop()?.toLowerCase();
            if (extension !== 'mp4') {
                error = 'Please upload an MP4 video.';
            } else if (file.size === 0) {
                error = 'Video cannot be empty.';
            } else if (file.size > 250 * 1024 * 1024) {
                error = 'Video must be 250 MiB or smaller.';
            } else if (index === 0) {
                try {
                    const duration = await new Promise((resolve, reject) => {
                        const video = document.createElement('video');
                        const url = URL.createObjectURL(file);

                        video.preload = 'metadata';
                        video.onloadedmetadata = () => {
                            const seconds = video.duration;
                            URL.revokeObjectURL(url);
                            resolve(seconds);
                        };
                        video.onerror = () => {
                            URL.revokeObjectURL(url);
                            reject(new Error('Unable to read video duration'));
                        };
                        video.src = url;
                    });

                    if (!Number.isFinite(duration)) {
                        error = 'Unable to determine the video duration.';
                    } else if (duration > 30) {
                        error = 'Short clip must be 30 seconds or less.';
                    }
                } catch {
                    error = 'Unable to read the video. Try another file.';
                }
            }
        }

        setErrors((current) =>
            current.map((item, i) => i === index ? error : item)
        );
        setFiles((current) =>
            current.map((item, i) => i === index ? (error ? null : file) : item)
        );
    };

    const count = files.filter(Boolean).length;

    const analyzeVideos = async () => {
        setMessageIndex(0);
        setAnalyzing(true);
        setApiError('');
        setProgressStep(1);
        setProcessingStage('Preparing your analysis...');

        try {
            const created = await createAnalysis({
                original: files[1],
                clip: files[0],
                useAi: true,
            });

            setProcessingStage('Uploading your videos...');
            await uploadAnalysisVideos(
                { original: files[1], clip: files[0] },
                created.uploads
            );

            setProgressStep(2);
            setProcessingStage('Submitting videos for processing...');
            await completeAnalysis(created.analysis_id);

            setProgressStep(3);
            setProcessingStage('Waiting for video processing...');

            const finished = await pollAnalysis(created.analysis_id, {
                intervalMs: 2000,
                timeoutMs: 15 * 60 * 1000,
                onUpdate: (updated) => {
                    if (updated.state === ANALYSIS_STATES.QUEUED) {
                        setProcessingStage('Your analysis is queued...');
                    } else if (updated.state === ANALYSIS_STATES.PROCESSING) {
                        setProcessingStage('Analyzing your videos...');
                    }
                },
            });

            if (finished.state === ANALYSIS_STATES.FAILED) {
                setApiError(
                    finished.error || 'Analysis processing failed. Please try again.'
                );
                return;
            }

            navigate(`/results/${created.analysis_id}`, {
                state: {
                    shortClip: files[0],
                    originalVideo: files[1],
                    analysis: finished,
                },
            });
        } catch (error) {
            console.error('Analysis failed:', error);
            setApiError(error.message || 'Something went wrong. Please try again.');
        } finally {
            setAnalyzing(false);
        }
    };

    const analyzeInstagram = async (event) => {
        event.preventDefault();
        setInstagramUrlError('');
        setApiError('');

        try {
            normalizeInstagramReelUrl(instagramUrl);
        } catch (error) {
            setInstagramUrlError(error.message);
            return;
        }

        setAnalyzing(true);
        setMessageIndex(0);
        setProgressStep(1);
        setProcessingStage('Submitting the Reel for analysis...');

        try {
            const created = await createInstagramFactCheck(instagramUrl);

            setProgressStep(3);
            setProcessingStage('Your Reel is queued...');

            const finished = await pollFactCheck(created.fact_check_id, {
                intervalMs: 4000,
                timeoutMs: 15 * 60 * 1000,
                onUpdate: (updated) => {
                    if (updated.status === FACT_CHECK_STATES.QUEUED) {
                        setProcessingStage('Your Reel is queued...');
                    } else if (updated.status === FACT_CHECK_STATES.PROCESSING) {
                        setProcessingStage('Analyzing the Reel...');
                    }
                },
            });

            navigate(`/fact-check-results/${created.fact_check_id}`, {
                state: { factCheck: finished },
            });
        } catch (error) {
            console.error('Instagram fact-check failed:', error);
            const retryMessage = error.retryAfter
                ? ` Try again in approximately ${error.retryAfter} seconds.`
                : '';
            setApiError(
                `${error.message || 'Unable to analyze this Reel.'}${retryMessage}`
            );
        } finally {
            setAnalyzing(false);
        }
    };

    return (
        <main className="analyze-page">
            <div className="upload-dialog analyze-card">
                <div className="dialog-shell">
                    <div className="dialog-head">
                        <div>
                            <p className="eyebrow">TRY CONTEXTLENS</p>
                            <h2>
                                {mode === 'instagram'
                                    ? 'Fact-check a Reel'
                                    : 'Add your videos'}
                            </h2>
                        </div>
                    </div>

                    <ToggleButtonGroup
                        value={mode}
                        exclusive
                        onChange={changeMode}
                        className="analysis-mode-toggle"
                        aria-label="Choose analysis type"
                        fullWidth
                    >
                        <ToggleButton value="videos">
                            <VideoLibraryOutlinedIcon />
                            <span className="mode-label-desktop">Compare videos</span>
                            <span className="mode-label-mobile">Videos</span>
                        </ToggleButton>
                        <ToggleButton value="instagram">
                            <InstagramIcon />
                            <span className="mode-label-desktop">Instagram Reel</span>
                            <span className="mode-label-mobile">Instagram</span>
                        </ToggleButton>
                    </ToggleButtonGroup>

                    {mode === 'videos' ? (
                        <>
                            <p className="dialog-copy">
                                Choose a short clip and its source recording.
                            </p>

                            <div className="upload-grid">
                                <UploadBox
                                    label="Short clip"
                                    file={files[0]}
                                    onFileChange={(file) => updateFile(0, file)}
                                    description="Choose a clip under 30 seconds"
                                    error={errors[0]}
                                    disabled={analyzing}
                                />
                                <UploadBox
                                    label="Original video"
                                    file={files[1]}
                                    onFileChange={(file) => updateFile(1, file)}
                                    description="Choose the full source recording"
                                    error={errors[1]}
                                    disabled={analyzing}
                                />
                            </div>

                            <div className="file-status" aria-live="polite">
                                {count === 2
                                    ? 'Both videos are ready for analysis.'
                                    : `${count} of 2 videos added.`}
                            </div>

                            <Button
                                type="button"
                                className="button analyze-button"
                                disabled={count !== 2 || analyzing}
                                onClick={analyzeVideos}
                            >
                                {analyzing ? (
                                    <>
                                        <CircularProgress size={18} color="inherit" />
                                        Processing...
                                    </>
                                ) : (
                                    <>Analyze videos <span>→</span></>
                                )}
                            </Button>
                        </>
                    ) : (
                        <form className="instagram-form" onSubmit={analyzeInstagram}>
                            <p className="dialog-copy">
                                Paste an authorized, publicly accessible Instagram Reel.
                                ContextLens will transcribe its audio and review factual
                                claims against cited evidence.
                            </p>

                            <TextField
                                label="Instagram Reel URL"
                                type="url"
                                value={instagramUrl}
                                onChange={(event) => {
                                    setInstagramUrl(event.target.value);
                                    setInstagramUrlError('');
                                }}
                                placeholder="https://www.instagram.com/reel/…/"
                                error={Boolean(instagramUrlError)}
                                helperText={
                                    instagramUrlError ||
                                    'Public Reels only. Private or login-only posts cannot be retrieved.'
                                }
                                disabled={analyzing}
                                autoComplete="off"
                                fullWidth
                            />

                            <div className="instagram-safety-note">
                                <strong>Before you continue</strong>
                                <span>
                                    Only submit content you have permission to analyze.
                                    Retrieval can fail if Instagram restricts access.
                                </span>
                            </div>

                            <Button
                                type="submit"
                                className="button analyze-button"
                                disabled={!instagramUrl.trim() || analyzing}
                            >
                                {analyzing ? (
                                    <>
                                        <CircularProgress size={18} color="inherit" />
                                        Processing...
                                    </>
                                ) : (
                                    <>Analyze Reel <span>→</span></>
                                )}
                            </Button>
                        </form>
                    )}

                    {analyzing && (
                        <div className="processing-message" role="status">
                            <div>
                                {progressStep < 3
                                    ? processingStage
                                    : loadingMessages[messageIndex]}
                            </div>
                            <p>
                                This may take several minutes. Please keep this page open.
                            </p>
                        </div>
                    )}

                    {apiError && (
                        <Alert severity="error" sx={{ mt: 2 }}>
                            {apiError}
                        </Alert>
                    )}
                </div>
            </div>
        </main>
    );
}

export default Analyze;
