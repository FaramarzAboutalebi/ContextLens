import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, CircularProgress, Alert } from '@mui/material';
import UploadBox from '../components/UploadBox';
import {
    ANALYSIS_STATES,
    createAnalysis,
    uploadAnalysisVideos,
    completeAnalysis,
    pollAnalysis,
} from '../services/api';

function Analyze() {
    const navigate = useNavigate();
    const [files, setFiles] = useState([null, null]);
    const [errors, setErrors] = useState(['', '']);
    const [analyzing, setAnalyzing] = useState(false);
    const [apiError, setApiError] = useState('');
    const [processingStage, setProcessingStage] = useState('');
    const [progressStep, setProgressStep] = useState(0);

    const loadingMessages = [
        'Analyzing your videos...',
        'Looking for matching speech...',
        'Finding the surrounding context...',
        'Still working on your analysis...',
    ];

    const [messageIndex, setMessageIndex] = useState(0);

    useEffect(() => {
        if (!analyzing || progressStep !== 3) return;

        setMessageIndex(0);

        const interval = setInterval(() => {
            setMessageIndex((current) =>
                (current + 1) % loadingMessages.length
            );
        }, 12000);

        return () => clearInterval(interval);
    }, [analyzing, progressStep]);

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

    const analyze = async () => {
        setAnalyzing(true);
        setApiError('');
        setProgressStep(1);
        setProcessingStage('Preparing your analysis...');

        try {
            // Create the analysis and get the upload instructions
            const created = await createAnalysis({
                original: files[1],
                clip: files[0],
                useAi: true,
            });

            setProcessingStage('Uploading your videos...');
            await uploadAnalysisVideos(
                {
                    original: files[1],
                    clip: files[0],
                },
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
                        setProcessingStage(
                            'Analyzing your videos... This may take several minutes. Please keep this page open.'
                        );
                    }
                },
            });

            if (finished.state === ANALYSIS_STATES.FAILED) {
                setApiError(
                    finished.error || 'Analysis processing failed. Please try again.'
                );
                return;
            }

            // Navigate to the results page
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

    return (
        <main className="analyze-page">
            <div className="upload-dialog">
                <div className="dialog-shell">
                <div className="dialog-head">
                    <div>
                    <p className="eyebrow">TRY CONTEXTLENS</p>
                    <h2>Add your videos</h2>
                    </div>
                </div>

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
                    onClick={analyze}
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