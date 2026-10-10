import { useState } from 'react';
import { ToggleButton, ToggleButtonGroup } from '@mui/material';
import AccessTimeRoundedIcon from '@mui/icons-material/AccessTimeRounded';
import GraphicEqRoundedIcon from '@mui/icons-material/GraphicEqRounded';

const exampleCases = {
  match: {
    label: 'Full Match',
    title: 'Example 1: Full Match',
    copy: 'A clean clip that appears in the original video.',
    status: 'Match found at 01:17',
    detail: 'The words and surrounding scene align with the source recording.',
  },
  context: {
    label: 'Context Change',
    title: 'Example 2: Context Changes the Meaning',
    copy: 'A true excerpt whose surrounding sentences add essential nuance.',
    status: 'Context expanded',
    detail: 'The nearby transcript shows what the speaker said immediately before and after.',
  },
  none: {
    label: 'No Match',
    title: 'Example 3: No Reliable Match',
    copy: 'The clip cannot be confidently located in the supplied recording.',
    status: 'No confident match',
    detail: 'ContextLens avoids presenting a weak result as evidence and asks for another source.',
  },
};

function ExamplesSection() {
  const [selected, setSelected] = useState('match');
  const example = exampleCases[selected];

  return <section className="examples" id="examples">
    <div className="examples-heading">
      <p className="eyebrow">EXAMPLES</p>
      <h2>See how it works<br />in <span>real cases.</span></h2>
      <p>Explore illustrative outcomes showing how ContextLens finds a matching segment and reveals the surrounding context.</p>
    </div>

    <ToggleButtonGroup
      className="example-tabs"
      exclusive
      value={selected}
      onChange={(_, value) => { if (value) setSelected(value); }}
      aria-label="Example type"
    >
      {Object.entries(exampleCases).map(([value, item]) =>
        <ToggleButton key={value} value={value}>{item.label}</ToggleButton>
      )}
    </ToggleButtonGroup>

    <article className="example-panel">
      <div className="example-copy">
        <h3>{example.title}</h3>
        <p>{example.copy}</p>
      </div>

      <div className="example-media-grid">
        <div>
          <strong>Short Clip (5s)</strong>
          <img src="/assets/short-clip.png" alt="Short illustrative video clip" />
        </div>
        <div>
          <strong>Original Video (23:40)</strong>
          <img src="/assets/original-video.png" alt="Illustrative original video" />
        </div>
      </div>

      <div className={`example-status ${selected}`}>
        <span>{selected === 'none' ? '!' : '✓'}</span>
        <div>
          <strong>{example.status}</strong>
          <p>{example.detail}</p>
        </div>
      </div>

      {selected !== 'none' && (
        <div className="example-metrics">
          <div>
            <AccessTimeRoundedIcon />
            <span>
              Found at<br />
              <strong>01:17 – 01:24</strong>
            </span>
          </div>
          <div>
            <GraphicEqRoundedIcon />
            <span>
              Text Similarity<br />
              <strong>99.4%</strong>
            </span>
          </div>
        </div>
      )}

    </article>
  </section>;
}

export default ExamplesSection;