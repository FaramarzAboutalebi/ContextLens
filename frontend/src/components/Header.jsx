import { useEffect, useState } from 'react';
import { Button, Drawer, IconButton } from '@mui/material';
import { Link } from 'react-router-dom';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import MenuRoundedIcon from '@mui/icons-material/MenuRounded';

function Header({ onTry }) {
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

  const openExamples = (event) => {
    event.preventDefault();
    closeMenu();
    window.history.pushState(null, '', '#examples');
    window.setTimeout(() => document.querySelector('#examples')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 250);
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
        onClick={() => setActiveSection('#home')}
      >
        Home
      </Link>

      <Link
        className={activeSection === '#how' ? 'active' : ''}
        to="/#how"
        onClick={() => setActiveSection('#how')}
      >
        How It Works
      </Link>

      <Link
        className={activeSection === '#examples' ? 'active' : ''}
        to="/#examples"
        onClick={() => setActiveSection('#examples')}
      >
        Examples
      </Link>

      <Link
        className={activeSection === '#about' ? 'active' : ''}
        to="/#about"
        onClick={() => setActiveSection('#about')}
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

        <Link to="/" onClick={closeMenu}>Home</Link>
        <Link to="/#how" onClick={closeMenu}>How It Works</Link>
        <Link to="/#examples" onClick={closeMenu}>Examples</Link>
        <Link to="/#about" onClick={closeMenu}>About</Link>

        <Button className="button" onClick={tryNow}>
          Try It Now →
        </Button>
      </nav>
    </Drawer>
  </header>;
}

export default Header;