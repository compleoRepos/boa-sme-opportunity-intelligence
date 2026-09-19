import { Download } from 'lucide-react'
import { useState } from 'react'
import { ApiError, apiDownload } from '../../api/client'
import { Button, useToast } from '../../ui'

export function ExportButton({ path, label = 'Exporter Excel' }: { path: string; label?: string }) {
  const [loading, setLoading] = useState(false)
  const toast = useToast()

  const download = async () => {
    if (loading) return
    setLoading(true)
    try {
      const result = await apiDownload(path)
      toast.push('success', 'Export Excel prêt', result.filename)
    } catch (error) {
      const detail = error instanceof ApiError && error.correlationId
        ? `${error.message} · Corrélation ${error.correlationId}`
        : error instanceof Error ? error.message : 'Le téléchargement a échoué.'
      toast.push('error', 'Export impossible', detail)
    } finally {
      setLoading(false)
    }
  }

  return <Button size="sm" icon={<Download size={14} />} loading={loading} onClick={() => void download()}>{label}</Button>
}
