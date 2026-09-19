import type { ReactNode } from 'react'

export function Tooltip({ content, children }: { content: ReactNode; children: ReactNode }) {
  return <span className="tip" tabIndex={0}>{children}<span className="tip-bubble" role="tooltip">{content}</span></span>
}
