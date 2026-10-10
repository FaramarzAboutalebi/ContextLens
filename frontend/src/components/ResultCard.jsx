function ResultCard() {
  return (
    <article className="result-card" id="match-result">
      <div className="result-title">
        <span className="check">✓</span>
        <strong>Match Found</strong>
      </div>

      <div className="result-media">
        <img
          src="/assets/match-found.png"
          alt="Matched segment and contextual transcript"
        />
      </div>
    </article>
  );
}

export default ResultCard;