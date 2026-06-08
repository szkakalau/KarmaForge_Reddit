import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

interface Props { children: ReactNode }
interface State { error: Error | null; errorInfo: ErrorInfo | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, errorInfo: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ errorInfo: info })
    console.error('ErrorBoundary caught:', error, info)

    // Report to Sentry if configured (lightweight, no npm dependency)
    const dsn = import.meta.env.VITE_SENTRY_DSN
    if (dsn) {
      const [proto, rest] = dsn.split('://')
      const [key, host] = (rest || '').split('@')
      const projectId = host?.split('/').pop() || ''
      const endpoint = `https://${host?.replace(`/${projectId}`, '')}/api/${projectId}/envelope/`
      try {
        const payload = {
          event_id: crypto.randomUUID(),
          timestamp: Date.now() / 1000,
          exception: {
            values: [{ type: error.name, value: error.message, stacktrace: { frames: [] } }],
          },
        }
        fetch(endpoint, {
          method: 'POST',
          headers: { 'X-Sentry-Auth': `Sentry sentry_version=7,sentry_key=${key}` },
          body: JSON.stringify(payload),
        }).catch(() => {})
      } catch { /* silent */ }
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex items-center justify-center min-h-screen bg-base">
          <div className="text-center max-w-md px-8">
            <div className="w-16 h-16 rounded-2xl bg-error/10 flex items-center justify-center mx-auto mb-6">
              <AlertTriangle size={28} className="text-error" />
            </div>
            <h1 className="text-xl font-semibold mb-3">Something went wrong</h1>
            <p className="text-sm text-text-secondary mb-2">
              {this.state.error.message || 'An unexpected error occurred.'}
            </p>
            {this.state.errorInfo && (
              <details className="text-xs text-text-muted mb-6 mt-4 bg-surface-1 rounded p-3 text-left max-h-32 overflow-auto">
                <summary className="cursor-pointer">Stack trace</summary>
                <pre className="mt-2 whitespace-pre-wrap">{this.state.errorInfo.componentStack}</pre>
              </details>
            )}
            <button
              onClick={() => { this.setState({ error: null, errorInfo: null }); window.location.reload() }}
              className="inline-flex items-center gap-2 bg-accent text-base font-semibold px-5 py-2.5 rounded-md text-sm hover:bg-accent-hover transition-colors"
            >
              <RefreshCw size={16} /> Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
