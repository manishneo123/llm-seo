import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { signup } from '../api/client';
import { useAuth } from '../context/useAuth';

export function Signup() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { setUser, setToken, token } = useAuth();
  const navigate = useNavigate();

  if (token) {
    navigate('/', { replace: true });
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    setSubmitting(true);
    try {
      const { token: t, user: u } = await signup(email.trim(), password, name.trim() || undefined);
      setToken(t);
      setUser(u);
      navigate('/', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign up failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page page">
      <header className="page-header">
        <h1 className="page-title">Sign up</h1>
      </header>
      <form onSubmit={handleSubmit} className="auth-form">
        {error && <p className="form-error auth-error">{error}</p>}
        <div className="form-group">
          <label htmlFor="signup-email" className="form-label">Email</label>
          <input
            id="signup-email"
            type="email"
            className="form-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
        </div>
        <div className="form-group">
          <label htmlFor="signup-password" className="form-label">Password (min 8 characters)</label>
          <input
            id="signup-password"
            type="password"
            className="form-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </div>
        <div className="form-group">
          <label htmlFor="signup-name" className="form-label">Name (optional)</label>
          <input
            id="signup-name"
            type="text"
            className="form-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Creating account…' : 'Sign up'}
          </button>
        </div>
      </form>
      <p className="auth-footer">
        Already have an account? <Link to="/signin">Sign in</Link>
      </p>
    </div>
  );
}
