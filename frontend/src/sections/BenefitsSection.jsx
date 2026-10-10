const benefits = [
  ['⌕', 'Find the matching segment', 'Locate where the clip appears in the original video.'],
  ['▤', 'Get the full context', 'See what was said before and after.'],
  ['≋', 'AI-powered transcription', 'Accurate timestamps and clear transcripts.'],
  ['⌘', 'Share evidence', 'Get a shareable link to show the full context.'],
];

function BenefitsSection() {
  return (
    <section className="benefits" aria-label="Key benefits">
      {benefits.map(([icon, title, copy]) => (
        <article key={title}>
          <span className="icon">{icon}</span>
          <div>
            <h2>{title}</h2>
            <p>{copy}</p>
          </div>
        </article>
      ))}
    </section>
  );
}

export default BenefitsSection;