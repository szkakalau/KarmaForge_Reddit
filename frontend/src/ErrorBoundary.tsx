import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props { children: ReactNode }
interface State { error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex items-center justify-center h-screen">
          <div className="text-center max-w-md">
            <h1 className="text-xl font-semibold mb-4">Something went wrong</h1>
            <p className="text-sm text-text-secondary mb-6">{this.state.error.message}</p>
            <button
              onClick={() => { this.setState({ error: null }); window.location.reload() }}
              className="bg-accent text-base font-semibold px-5 py-2.5 rounded-md text-sm hover:bg-accent-hover transition-colors"
            >
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
