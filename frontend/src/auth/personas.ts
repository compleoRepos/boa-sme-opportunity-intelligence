import type { DevPersona } from '../api/types'

/**
 * Personas de démonstration, utilisées UNIQUEMENT lorsque VITE_AUTH_DISABLED=true.
 * Elles rejouent un périmètre CC / agence / back-office contre le Gateway réel
 * (header X-Dev-Principal, ignoré dès que Keycloak est actif).
 */
export const DEV_PERSONAS: DevPersona[] = [
  {
    id: 'fund',
    label: 'Fonds Atlas Croissance',
    description: 'Investisseur externe · Financial Intelligence synthétique',
    subject: 'external-fund-a',
    username: 'fund.demo',
    clientId: 'boa-sme-spa',
    email: 'fund.demo@synthetic.invalid',
    displayName: 'Fonds Atlas Croissance',
    roles: ['EXTERNAL_CONSUMER'],
    scopes: ['financial.read', 'signals.read', 'opportunities.read', 'portfolio.read'],
  },
  {
    id: 'cc',
    label: 'Ahmed Mansouri',
    description: 'Chargé de clientèle PME · Agence Casablanca Anfa',
    subject: 'rm-01',
    username: 'ahmed.mansouri',
    email: 'ahmed.mansouri@synthetic.invalid',
    displayName: 'Ahmed Mansouri',
    roles: ['RELATIONSHIP_MANAGER'],
    relationshipManagerIds: ['rm-01'],
    branchIds: ['BR-01'],
  },
  {
    id: 'agence',
    label: 'Salma Berrada',
    description: 'Responsable d’agence · Casablanca Anfa',
    subject: 'bm-01',
    username: 'salma.berrada',
    displayName: 'Salma Berrada',
    roles: ['BRANCH_MANAGER'],
    branchIds: ['BR-01'],
  },
  {
    id: 'approbateur',
    label: 'Nadia Ouazzani',
    description: 'Approbatrice des règles · séparation des tâches',
    subject: 'approver-01',
    username: 'nadia.ouazzani',
    displayName: 'Nadia Ouazzani',
    roles: ['RULE_APPROVER', 'DATA_ANALYST'],
    branchIds: ['ALL'],
  },
  {
    id: 'ml-01',
    label: 'Karim Bennani',
    description: 'Responsable modèles · Digital Factory',
    subject: 'ml-01',
    username: 'karim.bennani',
    displayName: 'Karim Bennani',
    roles: ['ML_STEWARD', 'DATA_ANALYST'],
    branchIds: ['ALL'],
  },
  {
    id: 'backoffice',
    label: 'Youssef Tazi',
    description: 'Digital Factory · Rule Studio, ML governance, audit',
    subject: 'admin-01',
    username: 'youssef.tazi',
    displayName: 'Youssef Tazi',
    roles: ['ADMIN', 'BUSINESS_ANALYST', 'RULE_APPROVER', 'DATA_ANALYST'],
    branchIds: ['ALL'],
  },
]

export const PERSONA_STORAGE_KEY = 'boa.dev.persona'

export function personaHeader(persona: DevPersona) {
  return JSON.stringify({
    subject: persona.subject,
    username: persona.username,
    ...(persona.clientId ? { clientId: persona.clientId } : {}),
    ...(persona.email ? { email: persona.email } : {}),
    roles: persona.roles,
    scopes: persona.scopes ?? [],
    branchIds: persona.branchIds ?? [],
    relationshipManagerIds: persona.relationshipManagerIds ?? [],
  })
}
