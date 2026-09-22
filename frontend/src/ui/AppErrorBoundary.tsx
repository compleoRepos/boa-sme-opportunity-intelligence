import { Component, type ErrorInfo, type ReactNode } from 'react'

interface AppErrorBoundaryProps {
  children: ReactNode
}

interface AppErrorBoundaryState {
  failed: boolean
}

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = { failed: false }

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[BOA UI] Erreur de rendu interceptée', error, info.componentStack)
  }

  render() {
    if (this.state.failed) {
      return <main className="status-page" role="alert">
        <p className="eyebrow">Erreur d’affichage</p>
        <h1>Cette page n’a pas pu être affichée.</h1>
        <p className="muted">Les données n’ont pas été modifiées. Rechargez la page ou revenez au cockpit.</p>
        <div className="row" style={{ justifyContent: 'center' }}>
          <button className="btn primary" type="button" onClick={() => window.location.reload()}>Recharger la page</button>
          <a className="btn secondary" href="/">Revenir au cockpit</a>
        </div>
      </main>
    }
    return this.props.children
  }
}
