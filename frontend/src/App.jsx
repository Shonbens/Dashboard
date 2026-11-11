import { Briefcase, FileSearch, Layers3, Monitor, Moon, Sun } from 'lucide-react'
import useHashRoute, { navigate } from './lib/useHashRoute'
import useTheme from './lib/useTheme'
import ModelsHome from './components/models/ModelsHome'
import ModelEditor from './components/models/ModelEditor'
import PortfolioWorkspace from './components/PortfolioWorkspace'
import ProspectWorkspace from './components/prospect/ProspectWorkspace'

const SECTIONS = [
  { key: 'models', label: 'מודלים', icon: Layers3 },
  { key: 'portfolio', label: 'ניתוח תיק לקוח', icon: Briefcase },
  { key: 'prospect', label: 'ניתוח תיק פוטנציאלי', icon: FileSearch },
]
const THEMES = [
  { key: 'light', icon: Sun, label: 'בהיר' },
  { key: 'system', icon: Monitor, label: 'לפי המערכת' },
  { key: 'dark', icon: Moon, label: 'כהה' },
]

export default function App() {
  const [section = 'models', id] = useHashRoute()
  const [theme, setTheme] = useTheme()

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 bg-navy-900 text-white shadow-[0_1px_0_rgb(255_255_255/0.06)]">
        <div className="mx-auto flex h-16 max-w-[1440px] items-center justify-between gap-4 px-4 sm:px-6">
          <button onClick={() => navigate('/models')} className="flex items-center gap-4 text-right" aria-label="IBI – מסך המודלים">
            <img src="/ibi-logo.svg" alt="IBI" className="h-9 w-auto" />
            <span className="hidden h-8 w-px bg-white/15 sm:block" />
            <span className="hidden sm:block">
              <span className="block text-[15px] font-semibold leading-tight">ניהול תיקים</span>
              <span className="block text-xs text-white/55">מערכת מודלי השקעה</span>
            </span>
          </button>
          <div className="flex items-center gap-3">
            <nav className="flex rounded-xl bg-white/[0.07] p-1 text-sm">
              {SECTIONS.map(({ key, label, icon: Icon }) => (
                <button key={key} onClick={() => navigate(`/${key}`)} aria-current={section === key ? 'page' : undefined}
                  className={`inline-flex items-center gap-2 rounded-lg px-3 py-1.5 font-medium transition ${section === key ? 'bg-[#00ADDC] text-[#161932]' : 'text-white/70 hover:text-white'}`}>
                  <Icon className="h-4 w-4" /><span className="hidden sm:inline">{label}</span>
                </button>
              ))}
            </nav>
            <div className="hidden rounded-xl bg-white/[0.07] p-1 md:flex" role="radiogroup" aria-label="ערכת צבעים">
              {THEMES.map(({ key, icon: Icon, label }) => (
                <button key={key} onClick={() => setTheme(key)} title={label} aria-label={label} role="radio" aria-checked={theme === key}
                  className={`rounded-lg p-1.5 transition ${theme === key ? 'bg-white/15 text-white' : 'text-white/50 hover:text-white'}`}>
                  <Icon className="h-4 w-4" />
                </button>
              ))}
            </div>
          </div>
        </div>
        <div className="h-[3px] bg-gradient-to-l from-[#00ADDC] via-[#00ADDC]/60 to-transparent" />
      </header>

      {section === 'portfolio' ? (
        <PortfolioWorkspace />
      ) : section === 'prospect' ? (
        <ProspectWorkspace />
      ) : id ? (
        <ModelEditor key={id} modelId={Number(id)} />
      ) : (
        <ModelsHome />
      )}

      <footer className="mx-auto max-w-[1440px] px-6 pb-8 pt-2 text-xs text-slate-400">
        מחירים: Yahoo Finance · מאי״ה / הבורסה לני״ע בת״א · ביזפורטל. הנתונים לצורכי ניתוח בלבד ואינם מהווים ייעוץ השקעות.
      </footer>
    </div>
  )
}
