import UploadRoundedIcon from '@mui/icons-material/UploadRounded';
import GraphicEqRoundedIcon from '@mui/icons-material/GraphicEqRounded';
import DescriptionOutlinedIcon from '@mui/icons-material/DescriptionOutlined';
import ShareRoundedIcon from '@mui/icons-material/ShareRounded';

const steps = [
  [UploadRoundedIcon, 'Upload Videos', 'Add the short clip and the original video.'],
  [GraphicEqRoundedIcon, 'Find the Match', 'We transcribe the audio and locate where the clip appears in the original video.'],
  [DescriptionOutlinedIcon, 'See the Full Context', 'View what was said before and after, with accurate timestamps.'],
  [ShareRoundedIcon, 'Share Evidence', 'Get a shareable link to show the full context.'],
];

function HowItWorksSection() {
  return (
    <section className="how" id="how">
      <p className="eyebrow">HOW IT WORKS</p>

      <h2>
        Get the full context<br />
        in just <span>a few steps.</span>
      </h2>

      <p className="section-lede">
        Upload a short clip and the original video. ContextLens finds where
        the clip appears, transcribes the speech, and shows what was said
        before and after.
      </p>

      <div className="steps">
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