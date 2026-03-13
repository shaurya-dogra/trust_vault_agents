import { useState } from 'react'

const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function validateForm({ name, email, card }) {
  const errors = {}
  if (!name.trim()) errors.name = 'Name is required'
  if (!email.trim()) {
    errors.email = 'Email is required'
  } else if (!emailRegex.test(email)) {
    errors.email = 'Enter a valid email address'
  }
  if (!card.trim()) {
    errors.card = 'Card number is required'
  } else if (!/^\d{16}$/.test(card.replace(/\s/g, ''))) {
    errors.card = 'Card number must be 16 digits'
  }
  return errors
}

export default function App() {
  const [form, setForm] = useState({ name: '', email: '', card: '' })
  const [errors, setErrors] = useState({})
  const [submitted, setSubmitted] = useState(false)

  function handleChange(e) {
    const { name, value } = e.target
    if (name === 'card') {
      const digitsOnly = value.replace(/\D/g, '').slice(0, 16)
      setForm(f => ({ ...f, card: digitsOnly }))
    } else {
      setForm(f => ({ ...f, [name]: value }))
    }
    setErrors(err => ({ ...err, [name]: undefined }))
  }

  function handleSubmit(e) {
    e.preventDefault()
    const errs = validateForm(form)
    if (Object.keys(errs).length > 0) {
      setErrors(errs)
      return
    }
    setSubmitted(true)
  }

  if (submitted) {
    return (
      <div data-testid="success-message">
        <h2>Payment successful!</h2>
        <p>Thank you, {form.name}.</p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} noValidate data-testid="checkout-form">
      <h1>Checkout</h1>

      <label htmlFor="name">Full Name</label>
      <input
        id="name"
        name="name"
        type="text"
        value={form.name}
        onChange={handleChange}
        data-testid="input-name"
      />
      {errors.name && <span data-testid="error-name">{errors.name}</span>}

      <label htmlFor="email">Email</label>
      <input
        id="email"
        name="email"
        type="email"
        value={form.email}
        onChange={handleChange}
        data-testid="input-email"
      />
      {errors.email && <span data-testid="error-email">{errors.email}</span>}

      <label htmlFor="card">Card Number</label>
      <input
        id="card"
        name="card"
        type="text"
        value={form.card}
        onChange={handleChange}
        data-testid="input-card"
        maxLength={16}
        inputMode="numeric"
      />
      {errors.card && <span data-testid="error-card">{errors.card}</span>}

      <button type="submit" data-testid="submit-btn">Pay Now</button>
    </form>
  )
}
