import Header from './components/Header';
import Home from './pages/Home';
import Analyze from './pages/Analyze';
import Results from './pages/Results';
import { Routes, Route, useNavigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import {
  Alert,
  Snackbar,
} from '@mui/material';

import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded';

export default function App() {
  const navigate = useNavigate();

  const [activeTime, setActiveTime] = useState('01:17');
  const [toastText, setToastText] = useState('');
  useEffect(() => {
    if (!toastText) return undefined;
    const timer = window.setTimeout(() => setToastText(''), 2800);
    return () => window.clearTimeout(timer);
  }, [toastText]);
  const play = (time) => { setActiveTime(time); setToastText(`Demo playback started at ${time}`); };
  return <>
    <Header onTry={() => navigate('/analyze')} />
    <Routes>
      <Route
        path="/"
        element={
          <Home
            onTry={() => navigate('/analyze')}
            activeTime={activeTime}
            onPlay={play}
          />
        }
      />
      <Route path="/analyze" element={<Analyze />} />
      <Route path="/results/:analysisId" element={<Results />} />
    </Routes>

    <Snackbar open={Boolean(toastText)} autoHideDuration={2800} onClose={() => setToastText('')} anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}><Alert severity="info" variant="filled" icon={<PlayArrowRoundedIcon />} sx={{ borderRadius: 3 }}>{toastText}</Alert></Snackbar>
  </>;
}