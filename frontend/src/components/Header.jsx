import { useEffect, useState } from 'react';
import { Button, Drawer, IconButton } from '@mui/material';
import { Link, useNavigate } from 'react-router-dom';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import MenuRoundedIcon from '@mui/icons-material/MenuRounded';

function Header({ onTry }) {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeSection, setActiveSection] = useState(
    window.location.hash || '#home'
  );

  useEffect(() => {
    const updateActiveSection = () => {
      const sections = ['how', 'examples', 'about'];
      const headerOffset = 160;

      let current = '#home';

      for (const id of sections) {
        const element = document.getElementById(id);

        if (element && element.getBoundingClientRect().top <= headerOffset) {
          current = `#${id}`;
        }
      }

      setActiveSection(current);
    };

    window.addEventListener('scroll', updateActiveSection, { passive: true });
    window.addEventListener('hashchange', updateActiveSection);
    updateActiveSection();

    return () => {
      window.removeEventListener('scroll', updateActiveSection);
      window.removeEventListener('hashchange', updateActiveSection);
    };
  }, []);

  const closeMenu = () => {
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }

    setMenuOpen(false);
  };

  const tryNow = () => { closeMenu(); onTry(); };

  const openSection = (sectionId) => (event) => {
    event.preventDefault();
    const wasMenuOpen = menuOpen;
    closeMenu();
    setActiveSection(sectionId === 'home' ? '#home' : `#${sectionId}`);
    navigate(sectionId === 'home' ? '/' : `/#${sectionId}`);

    // MUI temporarily locks document scrolling while the mobile drawer closes.
    // Explicitly scroll after that transition, including when the hash is
    // already selected and React Router would otherwise have nothing to update.
    window.setTimeout(() => {
      if (sectionId === 'home') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      } else {
        document.getElementById(sectionId)?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      }
    }, wasMenuOpen ? 300 : 0);
  };

  return <header className="site-header">
    <Link className="brand" to="/" aria-label="ContextLens home">
      <span className="brand-mark" aria-hidden="true"><span /></span>
      <span>Context<span>Lens</span></span>
    </Link>

    <nav className="desktop-nav" aria-label="Primary navigation">
      <Link
        className={activeSection === '#home' ? 'active' : ''}
        to="/"
        onClick={openSection('home')}
      >
        Home
      </Link>

      <Link
        className={activeSection === '#how' ? 'active' : ''}
        to="/#how"
        onClick={openSection('how')}
      >
        How It Works
      </Link>

      <Link
        className={activeSection === '#examples' ? 'active' : ''}
        to="/#examples"
        onClick={openSection('examples')}
      >
        Examples
      </Link>

      <Link
        className={activeSection === '#about' ? 'active' : ''}
        to="/#about"
        onClick={openSection('about')}
      >
        About
      </Link>
    </nav>

    <Button className="button button-small desktop-cta" onClick={onTry}>
      Try It Now <span>→</span>
    </Button>

    <IconButton
      className="menu-button"
      aria-expanded={menuOpen}
      aria-controls="mobile-menu"
      aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
      onClick={(event) => {
        if (menuOpen) {
          closeMenu();
        } else {
          event.currentTarget.blur();
          setMenuOpen(true);
        }
      }}
    >
      <MenuRoundedIcon />
    </IconButton>

    <Drawer
      anchor="right"
      open={menuOpen}
      onClose={closeMenu}
      slotProps={{ paper: { id: 'mobile-menu', className: 'mobile-drawer' } }}
      sx={{
        '& .MuiDrawer-paper': {
          width: 'min(360px, 88vw)',
          boxSizing: 'border-box',
          padding: '12px',
          backgroundColor: '#fff',
        },
      }}
    >
      <nav className="mobile-menu" aria-label="Mobile navigation">
        <div className="drawer-head">
          <strong>ContextLens</strong>
          <IconButton onClick={closeMenu} aria-label="Close navigation">
            <CloseRoundedIcon />
          </IconButton>
        </div>

        <Link to="/" onClick={openSection('home')}>Home</Link>
        <Link to="/#how" onClick={openSection('how')}>How It Works</Link>
        <Link to="/#examples" onClick={openSection('examples')}>Examples</Link>
        <Link to="/#about" onClick={openSection('about')}>About</Link>

        <Button className="button" onClick={tryNow}>
          Try It Now →
        </Button>
      </nav>
    </Drawer>
  </header>;
}

export default Header;
