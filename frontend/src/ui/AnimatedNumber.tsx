import { useEffect, useRef, useState } from 'react'

const reduced = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

export function AnimatedNumber({ value, format, duration = 520 }: { value: number; format?: (value: number) => string; duration?: number }) {
  const [display, setDisplay] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    if (reduced() || !Number.isFinite(value)) { setDisplay(value); from.current = value; return }
    const start = performance.now()
    const origin = from.current
    let frame = 0
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(origin + (value - origin) * eased)
      if (progress < 1) frame = requestAnimationFrame(tick)
      else from.current = value
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value, duration])
  const rendered = format ? format(display) : Math.round(display).toLocaleString('fr-FR')
  return <span className="num">{rendered}</span>
}
