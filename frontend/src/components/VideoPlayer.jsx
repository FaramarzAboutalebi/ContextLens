function VideoPlayer({ title, src, poster }) {
    if (!src) return null;

    return (
        <div className="video-player">
            <h3>{title}</h3>

            <video
                controls
                preload="metadata"
                src={src}
                poster={poster || undefined}
            >
                Your browser does not support video playback.
            </video>
        </div>
    );
}

export default VideoPlayer;
