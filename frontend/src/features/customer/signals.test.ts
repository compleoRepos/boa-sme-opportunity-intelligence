import { describe, expect, it } from 'vitest'
import { parseReason, topSignals } from './signals'

const plain = (value?: string) => value?.replace(/\u202f|\u00a0/g, ' ')

describe('parseReason', () => {
  it('traduit une raison moteur en signal lisible et chiffré', () => {
    const parsed = parseReason('Inflow growth: observed=0.8583187563138814, condition=gt 0.25')
    expect(parsed.label).toBe('Encaissements')
    expect(plain(parsed.delta)).toBe('+86 %')
    expect(parsed.threshold).toBe(0.25)
    expect(plain(parsed.text)).toContain('seuil > 25 %')
  })

  it('reconnaît une condition booléenne sans inventer de pourcentage', () => {
    const parsed = parseReason('No recent investment financing: observed=True, condition=eq True')
    expect(parsed.isBoolean).toBe(true)
    expect(parsed.delta).toBeUndefined()
    expect(parsed.label).toBe('Aucun financement récent')
  })

  it('conserve un texte libre tel quel', () => {
    expect(parseReason('Texte libre du moteur').text).toBe('Texte libre du moteur')
  })

  it('ne garde que les signaux chiffrés dans le top', () => {
    const top = topSignals(['Inflow growth: observed=0.3, condition=gt 0.25', 'No recent investment financing: observed=True, condition=eq True', 'Supplier payment growth: observed=-0.1, condition=gt 0.2'], 3)
    expect(top.map((item) => plain(item.delta))).toEqual(['+30 %', '-10 %'])
  })
})
