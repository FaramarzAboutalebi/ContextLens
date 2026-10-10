function UploadBox({ label, file, onFileChange, description, error, disabled = false }) {
    return (
        <label className={`drop-zone ${file ? 'has-file' : ''}`}>
        <input
            type="file"
            accept=".mp4,video/mp4"
            disabled={disabled}
            onChange={(event) =>
                onFileChange(event.target.files[0] || null)
            }
        />

        <span className="upload-icon">↑</span>
        <strong>{label}</strong>

        <small>{error || file?.name || description}</small>

        <em>{disabled ? 'Analysis in progress...' : 'Browse file'}</em>
        </label>
    );
}

export default UploadBox;