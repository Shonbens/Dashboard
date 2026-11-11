import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { createModel, duplicateModel, getUser, setUser } from '../../lib/api'
import { navigate } from '../../lib/useHashRoute'
import Modal from './Modal'
import { TEMPLATES, newConfig } from '../../lib/allocation'

export default function NewModelDialog({ models, onClose }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [source, setSource] = useState('')
  const [kind, setKind] = useState('global') // 'global' | 'israel' (allocation sheet) | 'list'
  const [equity, setEquity] = useState('50')
  const [user, setU] = useState(getUser())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async (e) => {
    e?.preventDefault()
    if (!name.trim()) { setError('יש להזין שם למודל'); return }
    setBusy(true); setError(null); setUser(user)
    try {
      const m = source
        ? await duplicateModel(Number(source), name.trim(), user)
        : await createModel({
          name: name.trim(), description, holdings: [], user, note: 'יצירת מודל',
          ...(kind !== 'list' ? { config: newConfig(kind), equity_target: Number(equity) || 0 } : {}),
        })
      navigate(`/models/${m.id}`)
    } catch (err) { setError(err.message); setBusy(false) }
  }

  return (
    <Modal title="מודל חדש" subtitle="שם כמו ״70/30״ מזהה אוטומטית את יעד המניות" onClose={onClose}
      footer={<>
        <button className="btn-ghost" onClick={onClose}>ביטול</button>
        <button className="btn-primary" onClick={submit} disabled={busy}>{busy && <Loader2 className="h-4 w-4 animate-spin" />}יצירה ופתיחה בעורך</button>
      </>}>
      <form onSubmit={submit} className="space-y-4">
        <Field label="שם המודל"><input autoFocus className="input w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="לדוגמה: 70/30" /></Field>
        <Field label="תיאור (אופציונלי)"><input className="input w-full" value={description} onChange={(e) => setDescription(e.target.value)} disabled={!!source} placeholder="לדוגמה: מאוזן-צמיחה" /></Field>
        {!source && (
          <div className="grid grid-cols-3 gap-3">
            <Field label="סוג מודל">
              <select className="input w-full" value={kind} onChange={(e) => setKind(e.target.value)}>
                {Object.entries(TEMPLATES).map(([k, t]) => <option key={k} value={k}>גיליון הקצאה – {t.label}</option>)}
                <option value="list">רשימת ניירות פשוטה</option>
              </select>
            </Field>
            {kind !== 'list' && (
              <Field label="אחוז מנייתי">
                <input type="number" min="0" max="100" className="input num w-full" value={equity} onChange={(e) => setEquity(e.target.value)} />
              </Field>
            )}
          </div>
        )}
        <Field label="נקודת התחלה">
          <select className="input w-full" value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">מודל ריק (תבנית)</option>
            {models.map((m) => <option key={m.id} value={m.id}>העתקה ממודל {m.name}</option>)}
          </select>
        </Field>
        <Field label="שם העורך"><input className="input w-full" value={user} onChange={(e) => setU(e.target.value)} placeholder="יירשם בהיסטוריית הגרסאות" /></Field>
        {error && <p className="text-sm text-red-700">{error}</p>}
      </form>
    </Modal>
  )
}

export const Field = ({ label, children }) => (
  <label className="block"><span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>{children}</label>
)
