import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import App from './App'

describe('CheckoutForm — rendering', () => {
  it('renders all form fields and submit button', () => {
    render(<App />)
    expect(screen.getByTestId('input-name')).toBeInTheDocument()
    expect(screen.getByTestId('input-email')).toBeInTheDocument()
    expect(screen.getByTestId('input-card')).toBeInTheDocument()
    expect(screen.getByTestId('submit-btn')).toBeInTheDocument()
  })
})

describe('CheckoutForm — required field validation', () => {
  it('shows all required field errors on empty submit', () => {
    render(<App />)
    fireEvent.click(screen.getByTestId('submit-btn'))
    expect(screen.getByTestId('error-name')).toHaveTextContent('Name is required')
    expect(screen.getByTestId('error-email')).toHaveTextContent('Email is required')
    expect(screen.getByTestId('error-card')).toHaveTextContent('Card number is required')
  })

  it('clears error when user fills in the field', () => {
    render(<App />)
    fireEvent.click(screen.getByTestId('submit-btn'))
    fireEvent.change(screen.getByTestId('input-name'), {
      target: { name: 'name', value: 'Jane Doe' }
    })
    expect(screen.queryByTestId('error-name')).not.toBeInTheDocument()
  })
})

describe('CheckoutForm — email validation', () => {
  it('rejects invalid email format', () => {
    render(<App />)
    fireEvent.change(screen.getByTestId('input-email'), {
      target: { name: 'email', value: 'notanemail' }
    })
    fireEvent.click(screen.getByTestId('submit-btn'))
    expect(screen.getByTestId('error-email')).toHaveTextContent('valid email')
  })

  it('accepts valid email format', () => {
    render(<App />)
    fireEvent.change(screen.getByTestId('input-name'), {
      target: { name: 'name', value: 'Jane Doe' }
    })
    fireEvent.change(screen.getByTestId('input-email'), {
      target: { name: 'email', value: 'jane@example.com' }
    })
    fireEvent.change(screen.getByTestId('input-card'), {
      target: { name: 'card', value: '1234567890123456' }
    })
    fireEvent.click(screen.getByTestId('submit-btn'))
    expect(screen.queryByTestId('error-email')).not.toBeInTheDocument()
  })
})

describe('CheckoutForm — card number validation', () => {
  it('rejects card shorter than 16 digits', () => {
    render(<App />)
    fireEvent.change(screen.getByTestId('input-card'), {
      target: { name: 'card', value: '12345' }
    })
    fireEvent.click(screen.getByTestId('submit-btn'))
    expect(screen.getByTestId('error-card')).toHaveTextContent('16 digits')
  })

  it('only stores numeric characters in card field', () => {
    render(<App />)
    fireEvent.change(screen.getByTestId('input-card'), {
      target: { name: 'card', value: 'abcd1234efgh5678' }
    })
    expect(screen.getByTestId('input-card').value).toMatch(/^\d+$/)
  })
})

describe('CheckoutForm — successful submission', () => {
  it('shows success message after valid form submit', () => {
    render(<App />)
    fireEvent.change(screen.getByTestId('input-name'), {
      target: { name: 'name', value: 'Jane Doe' }
    })
    fireEvent.change(screen.getByTestId('input-email'), {
      target: { name: 'email', value: 'jane@example.com' }
    })
    fireEvent.change(screen.getByTestId('input-card'), {
      target: { name: 'card', value: '1234567890123456' }
    })
    fireEvent.click(screen.getByTestId('submit-btn'))
    expect(screen.getByTestId('success-message')).toBeInTheDocument()
  })
})
