function ContextFlags({ status }) {
    const messages = {
        MATCH_FOUND: {
        title: 'Match Found',
        description: 'Your clip was located in the original video.',
        icon: '✓',
        },
        NO_MATCH: {
            title: 'No Match Found',
            description: 'We could not confidently locate the clip in the original video.',
            icon: '!',
        },
        AMBIGUOUS_MATCH: {
            title: 'Multiple Possible Matches',
            description: 'Several segments could match your clip.',
            icon: '?',
        },
        ERROR: {
            title: 'Analysis Failed',
            description: 'Something went wrong while analyzing your videos.',
            icon: '!',
        },
    };

    const message = messages[status] || messages.ERROR;

    return (
        <div className={`results-status status-${status.toLowerCase()}`}>
        <span className="result-check">{message.icon}</span>

        <div>
            <h2>{message.title}</h2>
            <p>{message.description}</p>
        </div>
        </div>
    );
}

export default ContextFlags;