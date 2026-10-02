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

  it('rejects expired or malformed tokens', () => {
    expect(userFromToken(fakeToken({ sub: 'u', exp: 1 }))).toBeNull()
    expect(userFromToken('garbage')).toBeNull()
    expect(decodeJwt('a.b')).toBeNull()
  })
})
