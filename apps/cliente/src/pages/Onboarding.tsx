/** Onboarding in 3 steps: personal data -> DNI photo -> confirmation of extracted data. */
import {
  Alert,
  Button,
  Card,
  CardContent,
  errorMessage,
  Field,
  Input,
  Logo,
  type DniLookup,
  type OnboardingResult,
  Select,
  toast,
  useApi,
  useAuth,
} from '@chaski/shared'
import { Camera, CheckCircle2, CircleAlert, CircleHelp } from 'lucide-react'
import { type FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router'

const REGIONS = [
  'Lima',
  'Arequipa',
  'La Libertad',
  'Piura',
  'Cusco',
  'Junín',
  'Lambayeque',
  'Loreto',
]
const STEPS = ['Tus datos', 'Foto del DNI', 'Confirmación']

interface PersonalData {
  first_name: string
  last_name: string
  document_number: string
  birth_date: string
  email: string
  phone: string
  region: string
  monthly_income: string
}

const EMPTY: PersonalData = {
  first_name: '',
  last_name: '',
  document_number: '',
  birth_date: '',
  email: '',
  phone: '',
  region: 'Lima',
  monthly_income: '',
}

export function validatePersonal(d: PersonalData): Partial<Record<keyof PersonalData, string>> {
  const e: Partial<Record<keyof PersonalData, string>> = {}
  if (!d.first_name.trim()) e.first_name = 'Ingresa tus nombres'
  if (!d.last_name.trim()) e.last_name = 'Ingresa tus apellidos'
  if (!/^\d{8}$/.test(d.document_number)) e.document_number = 'El DNI tiene 8 dígitos'
  if (!d.birth_date) e.birth_date = 'Ingresa tu fecha de nacimiento'
  else {
    const age = (Date.now() - new Date(d.birth_date).getTime()) / (365.25 * 24 * 3600 * 1000)
    if (age < 18) e.birth_date = 'Debes ser mayor de edad'
  }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(d.email)) e.email = 'Correo inválido'
  if (!/^9\d{8}$/.test(d.phone)) e.phone = 'Celular de 9 dígitos que empieza con 9'
  return e
}

const CHECK_LABELS: Record<string, string> = {
  dni_coincide: 'Número de DNI',
  nombres_coinciden: 'Nombres y apellidos',
  fecha_nacimiento_coincide: 'Fecha de nacimiento',
  consulta_nombres_coinciden: 'Consulta de identidad',
  consulta_ocr_coinciden: 'Consulta vs foto del DNI',
}

function CheckIcon({ value }: { value: boolean | null }) {
  if (value === true)
    return <CheckCircle2 className="size-4 text-brand-600" aria-label="Coincide" />
  if (value === false)
    return <CircleAlert className="size-4 text-destructive" aria-label="No coincide" />
  return <CircleHelp className="size-4 text-muted-foreground" aria-label="No se pudo leer" />
}

export function OnboardingPage() {
  const api = useApi()
  const { mode, loginDev } = useAuth()
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [data, setData] = useState<PersonalData>(EMPTY)
  const [errors, setErrors] = useState<Partial<Record<keyof PersonalData, string>>>({})
  const [photo, setPhoto] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [looking, setLooking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<OnboardingResult | null>(null)

  const set = (k: keyof PersonalData) => (e: { target: { value: string } }) =>
    setData((d) => ({ ...d, [k]: e.target.value }))

  async function consultarDni() {
    if (!/^\d{8}$/.test(data.document_number)) {
      setErrors((e) => ({ ...e, document_number: 'El DNI tiene 8 dígitos' }))
      return
    }
    setLooking(true)
    setError(null)
    try {
      const res = await api.request<DniLookup>(
        'core',
        `/onboarding/lookup-dni/${data.document_number}`,
        { auth: false },
      )
      if (!res.available) {
        toast.error('No pudimos consultar el DNI ahora. Escribe tus datos.')
        return
      }
      if (!res.found || !res.nombres || !res.apellidos) {
        toast.error('No encontramos ese DNI. Revisa el número o escribe tus datos.')
        return
      }
      setData((d) => ({ ...d, first_name: res.nombres!, last_name: res.apellidos! }))
      setErrors((e) => {
        const next = { ...e }
        delete next.first_name
        delete next.last_name
        delete next.document_number
        return next
      })
      toast.success('Datos encontrados. Confirma que nombres y apellidos sean los tuyos.')
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLooking(false)
    }
  }

  function next(e: FormEvent) {
    e.preventDefault()
    const found = validatePersonal(data)
    setErrors(found)
    if (Object.keys(found).length === 0) setStep(1)
  }

  function onPhoto(file: File | null) {
    setError(null)
    if (file && file.size > 5 * 1024 * 1024) {
      setError('La imagen supera los 5 MB')
      return
    }
    setPhoto(file)
    setPreview(file ? URL.createObjectURL(file) : null)
  }

  async function submit() {
    if (!photo) return
    setBusy(true)
    setError(null)
    const form = new FormData()
    for (const [k, v] of Object.entries(data)) if (v) form.append(k, v)
    form.append('dni_image', photo)
    try {
      const res = await api.request<OnboardingResult>('core', '/onboarding', {
        method: 'POST',
        form,
        auth: false,
      })
      setResult(res)
      setStep(2)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  async function enterAsNewCustomer() {
    if (!result) return
    await loginDev({
      name: `${data.first_name} ${data.last_name}`,
      roles: ['Cliente'],
      customer_id: result.customer_id,
    })
    navigate('/', { replace: true })
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col gap-4 px-4 py-6">
      <div className="flex items-center justify-between">
        <Logo />
        <Link
          to="/bienvenida"
          className="text-sm font-medium text-secondary underline dark:text-navy-300"
        >
          Volver
        </Link>
      </div>
      <ol className="grid grid-cols-3 gap-2" aria-label="Pasos del registro">
        {STEPS.map((s, i) => (
          <li
            key={s}
            aria-current={i === step ? 'step' : undefined}
            className="flex flex-col gap-1"
          >
            <span className={`h-1.5 rounded-full ${i <= step ? 'bg-primary' : 'bg-muted'}`} />
            <span className={`text-xs ${i === step ? 'font-semibold' : 'text-muted-foreground'}`}>
              {i + 1}. {s}
            </span>
          </li>
        ))}
      </ol>

      {step === 0 && (
        <form onSubmit={next} className="flex flex-col gap-3" noValidate>
          <h1 className="text-xl font-bold">Abre tu cuenta Chaski</h1>
          <Field label="Nombres" error={errors.first_name}>
            {(p) => (
              <Input
                {...p}
                value={data.first_name}
                onChange={set('first_name')}
                autoComplete="given-name"
              />
            )}
          </Field>
          <Field label="Apellidos" error={errors.last_name}>
            {(p) => (
              <Input
                {...p}
                value={data.last_name}
                onChange={set('last_name')}
                autoComplete="family-name"
              />
            )}
          </Field>
          <Field
            label="DNI"
            error={errors.document_number}
            hint="8 dígitos. Consultar rellena nombres y apellidos para que los confirmes."
          >
            {(p) => (
              <div className="flex gap-2">
                <Input
                  {...p}
                  className="flex-1"
                  value={data.document_number}
                  onChange={set('document_number')}
                  inputMode="numeric"
                  maxLength={8}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => void consultarDni()}
                  disabled={data.document_number.length !== 8}
                  loading={looking}
                >
                  Consultar
                </Button>
              </div>
            )}
          </Field>
          <Field label="Fecha de nacimiento" error={errors.birth_date}>
            {(p) => (
              <Input {...p} type="date" value={data.birth_date} onChange={set('birth_date')} />
            )}
          </Field>
          <Field label="Correo electrónico" error={errors.email}>
            {(p) => (
              <Input
                {...p}
                type="email"
                value={data.email}
                onChange={set('email')}
                autoComplete="email"
              />
            )}
          </Field>
          <Field label="Celular" error={errors.phone}>
            {(p) => (
              <Input
                {...p}
                value={data.phone}
                onChange={set('phone')}
                inputMode="tel"
                maxLength={9}
                autoComplete="tel"
              />
            )}
          </Field>
          <Field label="Región">
            {(p) => (
              <Select {...p} value={data.region} onChange={set('region')}>
                {REGIONS.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Ingreso mensual (opcional)" hint="Nos ayuda a ofrecerte mejores préstamos">
            {(p) => (
              <Input
                {...p}
                value={data.monthly_income}
                onChange={set('monthly_income')}
                inputMode="decimal"
              />
            )}
          </Field>
          {error && <Alert variant="danger">{error}</Alert>}
          <Button type="submit" size="lg" className="mt-2">
            Continuar
          </Button>
        </form>
      )}

      {step === 1 && (
        <div className="flex flex-col gap-4">
          <h1 className="text-xl font-bold">Toma una foto de tu DNI</h1>
          <p className="text-sm text-muted-foreground">
            Usa buena luz, sin reflejos, y que se vean los 4 bordes del documento.
          </p>
          <label className="flex min-h-48 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed bg-card p-4 text-center focus-within:outline-2 focus-within:outline-ring">
            {preview ? (
              <img
                src={preview}
                alt="Vista previa del DNI"
                className="max-h-56 rounded-lg object-contain"
              />
            ) : (
              <>
                <Camera className="size-10 text-muted-foreground" aria-hidden />
                <span className="font-medium">Tomar o subir foto</span>
                <span className="text-xs text-muted-foreground">JPG, PNG o WEBP · máx. 5 MB</span>
              </>
            )}
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              className="sr-only"
              onChange={(e) => onPhoto(e.target.files?.[0] ?? null)}
              aria-label="Foto del DNI"
            />
          </label>
          {error && <Alert variant="danger">{error}</Alert>}
          <div className="grid grid-cols-2 gap-2">
            <Button variant="outline" size="lg" onClick={() => setStep(0)} disabled={busy}>
              Atrás
            </Button>
            <Button size="lg" onClick={() => void submit()} disabled={!photo} loading={busy}>
              Enviar
            </Button>
          </div>
        </div>
      )}

      {step === 2 && result && (
        <div className="flex flex-col gap-4">
          <h1 className="text-xl font-bold">Confirma tus datos</h1>
          {result.lookup && (
            <p className="text-sm text-muted-foreground">
              Consulta de identidad ({result.lookup.fuente}): {result.lookup.nombres}{' '}
              {result.lookup.apellidos}
            </p>
          )}
          {result.extracted ? (
            <Card>
              <CardContent className="pt-4">
                <p className="mb-2 text-sm text-muted-foreground">
                  Esto es lo que leímos de tu DNI
                  {result.confidence != null &&
                    ` (confianza ${Math.round(result.confidence * 100)} %)`}
                  :
                </p>
                <dl className="space-y-1 text-sm">
                  {Object.entries(result.extracted)
                    .filter(([k]) => k !== 'modelo')
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2">
                        <dt className="capitalize text-muted-foreground">{k.replace(/_/g, ' ')}</dt>
                        <dd className="font-medium">{v}</dd>
                      </div>
                    ))}
                </dl>
                <ul className="mt-3 space-y-1 border-t pt-3 text-sm">
                  {Object.entries(result.checks).map(([k, v]) => (
                    <li key={k} className="flex items-center gap-2">
                      <CheckIcon value={v} /> {CHECK_LABELS[k] ?? k}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : (
            <Alert variant="info">
              No pudimos leer tu DNI automáticamente. Un asesor revisará la foto manualmente.
            </Alert>
          )}
          {Object.values(result.checks).includes(false) && (
            <Alert variant="warning">
              Algunos datos no coinciden con lo que escribiste. Un asesor lo revisará; no necesitas
              hacer nada más.
            </Alert>
          )}
          <Alert variant="success">{result.message}</Alert>
          {mode === 'dev' ? (
            <Button size="lg" onClick={() => void enterAsNewCustomer()}>
              Ingresar a mi cuenta
            </Button>
          ) : (
            <Button size="lg" asChild>
              <Link to="/bienvenida">Volver al inicio</Link>
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
