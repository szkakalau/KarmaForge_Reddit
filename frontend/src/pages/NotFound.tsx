import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <p className="font-mono text-[72px] font-bold text-text-muted/30 mb-4">404</p>
        <h1 className="text-xl font-semibold mb-2">Page not found</h1>
        <p className="text-text-secondary text-sm mb-8">
          The page you're looking for doesn't exist or has been moved.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 bg-accent text-base font-semibold px-5 py-2.5 rounded-md text-sm hover:bg-accent-hover transition-colors"
        >
          <ArrowLeft size={16} /> Back to Home
        </Link>
      </div>
    </div>
  )
}
