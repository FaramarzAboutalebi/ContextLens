import VisibilityOutlinedIcon from '@mui/icons-material/VisibilityOutlined';
import GroupsOutlinedIcon from '@mui/icons-material/GroupsOutlined';
import ShieldOutlinedIcon from '@mui/icons-material/ShieldOutlined';
import FavoriteRoundedIcon from '@mui/icons-material/FavoriteRounded';

const missionPoints = [
  [VisibilityOutlinedIcon, 'Transparency', 'We make it easy to see the full context behind a clip.'],
  [GroupsOutlinedIcon, 'Accessibility', 'Anyone can use ContextLens — no account required.'],
  [ShieldOutlinedIcon, 'Responsible AI', 'We focus on clear, factual transcripts and contextual insights, without making claims about truth or intent.'],
];

function AboutSection() {
  return (
    <section className="about" id="about">
      <div className="about-intro">
        <p className="eyebrow">ABOUT</p>

        <h2>
          Our mission<br />
          for a more informed<br />
          <span>online world.</span>
        </h2>

        <p>
          ContextLens was built to help people understand video clips in context.
          In a world where short clips are often shared out of context, we provide
          the tools to see the bigger picture.
        </p>
      </div>

      <div className="mission-list">
        {missionPoints.map(([MissionIcon, title, copy]) => (
          <article key={title}>
            <span><MissionIcon /></span>
            <div>
              <h3>{title}</h3>
              <p>{copy}</p>
            </div>
          </article>
        ))}
      </div>

      <aside className="about-callout">
        <span><FavoriteRoundedIcon /></span>
        <div>
          <h3>Built for curious people</h3>
          <p>
            Whether you're a student, researcher, content creator, or just
            someone who wants to understand the full story, ContextLens is
            here to help.
          </p>
        </div>
      </aside>
    </section>
  );
}

export default AboutSection;