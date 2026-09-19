import { label, setRuntimeLabels } from './format'

describe('catalogue de libellés runtime', () => {
  afterEach(() => setRuntimeLabels())

  it('surcharge un libellé connu sans modifier le code', () => {
    setRuntimeLabels({ OPEN: 'À traiter' })
    expect(label('OPEN')).toBe('À traiter')
    expect(label('P1')).toBe('Priorité P1')
  })

  it('revient au dictionnaire embarqué quand le catalogue est indisponible', () => {
    setRuntimeLabels()
    expect(label('OPEN')).toBe('Ouvert')
  })
})
