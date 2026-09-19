import type { ReactNode } from 'react'

export function Panel({ eyebrow, title, tools, children, className = '', flush, tight, id, 'data-demo': demo }: { eyebrow?: string; title?: ReactNode; tools?: ReactNode; children: ReactNode; className?: string; flush?: boolean; tight?: boolean; id?: string; 'data-demo'?: string }) {
  return <section className={`panel ${className}`} id={id} data-demo={demo} aria-labelledby={title && id ? `${id}-title` : undefined}>
    {(title || tools) && <header className="panel-head">
      <div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}{title && <h2 id={id ? `${id}-title` : undefined}>{title}</h2>}</div>
      {tools && <div className="panel-tools">{tools}</div>}
    </header>}
    <div className={flush ? '' : `panel-body ${tight ? 'tight' : ''}`}>{children}</div>
  </section>
}
