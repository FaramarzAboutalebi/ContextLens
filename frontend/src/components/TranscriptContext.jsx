function TranscriptContext({ before, during, after }) {
  return (
    <>
      <h2>Full Context</h2>

      <div className="context-block">
        <span>BEFORE</span>
        <p>{before}</p>
      </div>

      <div className="context-block during">
        <span>DURING THE CLIP</span>
        <p>{during}</p>
      </div>

      <div className="context-block">
        <span>AFTER</span>
        <p>{after}</p>
      </div>
    </>
  );
}

export default TranscriptContext;