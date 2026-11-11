import { useState } from 'react'
import { CheckCircle2, FileText, Loader2 } from 'lucide-react'
import { clientReportPdf, getUser, setUser } from '../lib/api'
import Modal from './models/Modal'
import { Field } from './models/NewModelDialog'

const INCLUDED = [
  'התיק במבט אחד – שווי, חשיפה למניות ולדולר, במילים פשוטות',
  'איפה הכסף מושקע – לפי סוג השקעה ולפי אזור בעולם',
  'הסבר פשוט לכל השקעה בתיק',
  'השוואה למודל ההשקעה הקרוב ביותר של IBI',
  'מה יכול לקרות לתיק בתרחישים לדוגמה – בשקלים',
  'עלויות, מילון מונחים וגילוי נאות',
]

export default function ClientReportDialog({ rows, aum, onClose }) {
  const [client, setClient] = useState('')
  const [advisor, setAdvisor] = useState(getUser())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [url, setUrl] = useState(null)

  const generate = async (e) => {
    e?.preventDefault()
    setBusy(true); setError(null)
    if (advisor) setUser(advisor)
    try {
      const blob = await clientReportPdf(rows, aum, client.trim(), advisor.trim())
      const u = URL.createObjectURL(blob)
      setUrl(u)
      const a = document.createElement('a')
      a.href = u
      a.download = `IBI_client_report_${new Date().toISOString().slice(0, 10)}.pdf`
      a.click()
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const close = () => { if (url) URL.revokeObjectURL(url); onClose() }

  return (
    <Modal title="דוח אישי ללקוח" subtitle="דוח PDF בשפה פשוטה, בעיצוב IBI, להצגה ולשליחה ללקוח" onClose={close}
      footer={<>
        <button className="btn-ghost" onClick={close}>סגירה</button>
        <button className="btn-primary" onClick={generate} disabled={busy || !rows.length}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}{url ? 'הפקה מחדש' : 'הפקת הדוח'}
        </button>
      </>}>
      <form onSubmit={generate} className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="שם הלקוח (אופציונלי)"><input autoFocus className="input w-full" value={client} onChange={(e) => setClient(e.target.value)} placeholder="יופיע בפתיחת הדוח" /></Field>
          <Field label="שם מנהל התיק"><input className="input w-full" value={advisor} onChange={(e) => setAdvisor(e.target.value)} /></Field>
        </div>
        <div className="rounded-xl bg-slate-50 p-4">
          <div className="mb-2 text-sm font-semibold text-slate-700">מה בדוח</div>
          <ul className="space-y-1.5 text-sm text-slate-600">
            {INCLUDED.map((t) => <li key={t} className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />{t}</li>)}
          </ul>
        </div>
        <p className="text-xs text-slate-500">שם הלקוח משמש רק בתוך קובץ ה-PDF ואינו נשמר במערכת. השווי בדוח מחושב לפי היקף הנכסים שהוזן (<span className="num">₪{Math.round(aum).toLocaleString('en-US')}</span>).</p>
        {url && <p className="text-sm text-emerald-700">הדוח הופק והורד. <a href={url} target="_blank" rel="noopener" className="font-medium underline">פתיחה בלשונית חדשה</a></p>}
        {error && <p className="text-sm text-red-700">{error}</p>}
      </form>
    </Modal>
  )
}
