import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useState } from 'react'
import AppLayout from './components/layout/AppLayout'
import Chat from './pages/Chat'
import Diary from './pages/Diary'
import Profile from './pages/Profile'
import Timeline from './pages/Timeline'
import Knowledge from './pages/Knowledge'
import Import from './pages/Import'
import SettingsPage from './pages/Settings'
import Character from './pages/Character'
import Monitor from './pages/Monitor'
import Portraits from './pages/Portraits'
import Insight from './pages/Insight'
import QuickNote from './pages/QuickNote'
import Welcome from './pages/Welcome'

function App() {
  const [showWelcome, setShowWelcome] = useState(() => !sessionStorage.getItem('welcome_dismissed'))

  const dismissWelcome = () => {
    sessionStorage.setItem('welcome_dismissed', '1')
    setShowWelcome(false)
  }

  return (
    <BrowserRouter>
      {showWelcome ? (
        <Welcome onDismiss={dismissWelcome} />
      ) : (
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<Chat />} />
            <Route path="/diary" element={<Diary />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/character" element={<Character />} />
            <Route path="/timeline" element={<Timeline />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/import" element={<Import />} />
            <Route path="/monitor" element={<Monitor />} />
            <Route path="/portraits" element={<Portraits />} />
            <Route path="/insight" element={<Insight />} />
            <Route path="/quicknote" element={<QuickNote />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Routes>
      )}
    </BrowserRouter>
  )
}

export default App
