import React from 'react'
import { AlertOctagon } from 'lucide-react'

export default class ErrorBoundary extends React.Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  componentDidCatch(error, info) { console.error('UI error', error, info) }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="min-h-screen grid place-items-center p-6">
        <div className="card max-w-md p-8 text-center">
          <AlertOctagon className="mx-auto mb-3 h-10 w-10 text-red-500" />
          <h2 className="mb-2 text-lg font-semibold">אירעה שגיאה בתצוגה</h2>
          <p className="mb-5 text-sm text-slate-500">{String(this.state.error?.message || this.state.error)}</p>
          <button className="btn-primary" onClick={() => this.setState({ error: null })}>נסה שוב</button>
        </div>
      </div>
    )
  }
}
