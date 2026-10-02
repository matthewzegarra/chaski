import { decodeJwt, userFromToken } from './AuthProvider'

function fakeToken(claims: Record<string, unknown>): string {
  const enc = (o: unknown) =>
    btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(o))))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
  return `${enc({ alg: 'HS256' })}.${enc(claims)}.sig`
}

describe('userFromToken', () => {
  const future = Math.floor(Date.now() / 1000) + 3600

  it('reads roles, name with accents and customer_id', () => {
    const user = userFromToken(
      fakeToken({
        sub: 'u1',
        name: 'María Quispe',
        roles: ['Cliente'],
        customer_id: 'c-1',
        exp: future,
      }),
    )
    expect(user).toEqual({ sub: 'u1', name: 'María Quispe', roles: ['Cliente'], customerId: 'c-1' })
  })

  it('prefers Entra oid and supports extension_customer_id', () => {
    const user = userFromToken(
      fakeToken({
        sub: 's',
        oid: 'o',
        roles: ['Admin'],
        extension_customer_id: 'c-2',
        exp: future,
      }),
    )
    expect(user?.sub).toBe('o')
    expect(user?.customerId).toBe('c-2')
  })

  it.each(['extn.customer_id', 'extension_c386a571a8b44de7a54a4e58adc7ff45_customer_id'])(
    'reads customer_id from the Entra directory extension claim %s',
    (claim) => {
      const user = userFromToken(fakeToken({ oid: 'o', roles: ['Cliente'], [claim]: 'c-3', exp: future }))
      expect(user?.customerId).toBe('c-3')
    },
  )

  it('rejects expired or malformed tokens', () => {
    expect(userFromToken(fakeToken({ sub: 'u', exp: 1 }))).toBeNull()
    expect(userFromToken('garbage')).toBeNull()
    expect(decodeJwt('a.b')).toBeNull()
  })
})
