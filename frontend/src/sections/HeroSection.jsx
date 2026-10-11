import { Button } from '@mui/material';
import InstagramIcon from '@mui/icons-material/Instagram';
import VideoLibraryOutlinedIcon from '@mui/icons-material/VideoLibraryOutlined';
import ResultCard from '../components/ResultCard';

function HeroSection({ onTry, activeTime, onPlay }) {
  return (
    <section className="hero">
      <div className="glow glow-one" />
      <div className="glow glow-two" />

      <div className="hero-copy">
        <p className="eyebrow">FIND THE FULL STORY</p>
        <h1>
          Understand<br />
          video clips in<br />
          <span>full context.</span>
        </h1>

        <p className="lede">
          Upload a short clip and the original video. ContextLens finds
          where the clip appears, transcribes the speech, and shows what
          was said before and after.
        </p>

        <div className="hero-capabilities" aria-label="What ContextLens supports">
          <p>WHAT CONTEXTLENS SUPPORTS</p>
          <div>
            <span className="hero-capability-icon" aria-hidden="true">
              <VideoLibraryOutlinedIcon />
            </span>
            <span>
              <strong>Compare video clips</strong>
              <small>Find the source match and surrounding context.</small>
            </span>
          </div>
          <div>
            <span className="hero-capability-icon" aria-hidden="true">
              <InstagramIcon />
            </span>
            <span>
              <strong>Fact-check Instagram Reels</strong>
              <small>Review factual claims with timestamped, cited evidence.</small>
            </span>
          </div>
        </div>

        <div className="hero-actions desktop-hero-actions">
          <Button className="button hero-button" onClick={onTry}>
            Try It Now <span>→</span>
          </Button>
          <p className="microcopy">No account required. Free to use.</p>
        </div>
      </div>

      <div
        className="hero-demo"
        aria-label="Illustration of ContextLens matching a clip to its original video"
      >
        <div className="source-stack">
          <article className="mini-card short">
            <span className="tag red">Short Clip (5s)</span>
            <img
              src="/assets/short-clip.png"
              alt="Short video clip of a speaker"
            />
            </article>

            <div className="source-arrow" aria-hidden="true">↓</div>

            <article className="mini-card original">
              <span className="tag purple">Original Video (23:40)</span>
            <img
              src="/assets/original-video.png"
              alt="Original long video of the same speaker"
            />
          </article>
        </div>

        <div className="match-arrow" aria-hidden="true">→</div>

        <div className="hero-actions mobile-hero-actions">
          <Button className="button hero-button" onClick={onTry}>
            Try It Now <span>→</span>
          </Button>
          <p className="microcopy">No account required. Free to use.</p>
        </div>

        <ResultCard activeTime={activeTime} onPlay={onPlay} />
      </div>
    </section>
  );
}

export default HeroSection;
