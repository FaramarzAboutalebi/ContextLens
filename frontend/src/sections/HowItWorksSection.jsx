import { useState } from 'react';
import UploadRoundedIcon from '@mui/icons-material/UploadRounded';
import GraphicEqRoundedIcon from '@mui/icons-material/GraphicEqRounded';
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined';
import ShareRoundedIcon from '@mui/icons-material/ShareRounded';
import InstagramIcon from '@mui/icons-material/Instagram';
import LinkRoundedIcon from '@mui/icons-material/LinkRounded';
import SubtitlesRoundedIcon from '@mui/icons-material/SubtitlesRounded';
import FactCheckRoundedIcon from '@mui/icons-material/FactCheckRounded';
import SourceRoundedIcon from '@mui/icons-material/SourceRounded';
import VideoLibraryOutlinedIcon from '@mui/icons-material/VideoLibraryOutlined';

const comparisonSteps = [
  [UploadRoundedIcon, 'Upload Videos', 'Add the short clip and the original video.'],
  [GraphicEqRoundedIcon, 'Find the Match', 'We transcribe the audio and locate where the clip appears in the original video.'],
  [DescriptionOutlinedIcon, 'See the Full Context', 'View what was said before and after, with accurate timestamps.'],
  [ShareRoundedIcon, 'Share Evidence', 'Get a shareable link to show the full context.'],
];

const instagramSteps = [
  [LinkRoundedIcon, 'Paste a Reel URL', 'Add the link to a public Instagram Reel.'],
  [SubtitlesRoundedIcon, 'Transcribe the Reel', 'We retrieve the Reel and turn its spoken content into timestamped text.'],
  [FactCheckRoundedIcon, 'Review the Claims', 'Factual claims are checked against relevant external evidence.'],
  [SourceRoundedIcon, 'Explore the Evidence', 'See verdicts, explanations, timestamps, and clickable source citations.'],
];

function HowItWorksSection() {
  const [workflow, setWorkflow] = useState('comparison');
  const isInstagram = workflow === 'instagram';
  const steps = isInstagram ? instagramSteps : comparisonSteps;

  return (
    <section className="how" id="how">
      <p className="eyebrow">HOW IT WORKS</p>

      <h2>
        Get the full context<br />
        in just <span>a few steps.</span>
      </h2>

      <p className="section-lede">
        {isInstagram
          ? 'Paste a public Instagram Reel URL. ContextLens transcribes its claims and presents evidence-backed findings with citations.'
          : 'Upload a short clip and the original video. ContextLens finds where the clip appears, transcribes the speech, and shows what was said before and after.'}
      </p>

      <div className="how-workflow-switch" aria-label="Choose a ContextLens workflow">
        <button
          type="button"
          className={!isInstagram ? 'active' : ''}
          aria-pressed={!isInstagram}
          onClick={() => setWorkflow('comparison')}
        >
          <VideoLibraryOutlinedIcon aria-hidden="true" />
          Compare Videos
        </button>
        <button
          type="button"
          className={isInstagram ? 'active' : ''}
          aria-pressed={isInstagram}
          onClick={() => setWorkflow('instagram')}
        >
          <InstagramIcon aria-hidden="true" />
          Instagram Reel
        </button>
      </div>

      <div className="steps" key={workflow}>
        {steps.map(([StepIcon, title, copy], index) => (
          <span className="step-fragment" key={title}>
            <span className="step-number">{index + 1}</span>

            <article>
              <span className="step-icon">
                <StepIcon />
              </span>

              <div>
                <h3>{title}</h3>
                <p>{copy}</p>
              </div>
            </article>

            {index < steps.length - 1 && <b aria-hidden="true">→</b>}
          </span>
        ))}
      </div>
    </section>
  );
}

export default HowItWorksSection;
