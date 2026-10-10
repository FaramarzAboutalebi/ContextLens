import HeroSection from '../sections/HeroSection';
import BenefitsSection from '../sections/BenefitsSection';
import HowItWorksSection from '../sections/HowItWorksSection';
import ExamplesSection from '../sections/ExamplesSection';
import AboutSection from '../sections/AboutSection';
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

function Home({ onTry, activeTime, onPlay }) {
    const location = useLocation();

    useEffect(() => {
        const sectionId = location.hash.slice(1);

        if (sectionId) {
        document.getElementById(sectionId)?.scrollIntoView({
            behavior: 'smooth',
        });
        } else {
        window.scrollTo({ top: 0 });
        }
    }, [location.pathname, location.hash]);

    return (
        <main>
            <div className="home-view" id="home">
                <HeroSection
                onTry={onTry}
                activeTime={activeTime}
                onPlay={onPlay}
                />

                <BenefitsSection />
            </div>

            <HowItWorksSection />
            <ExamplesSection />
            <AboutSection />
        </main>
  );
}

export default Home;