import { useState } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { signin } from '../api/client';
import { useAuth } from '../context/AuthContext';

export function Signin() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { setUser, setToken, token } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/';

  if (token) {
    navigate(from, { replace: true });
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const { token: t, user: u } = await signin(email.trim(), password);
      setToken(t);
      setUser(u);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="auth-page page">
      <header className="page-header">
        <h1 className="page-title">Sign in</h1>
      </header>
      <form onSubmit={handleSubmit} className="auth-form">
        {error && <p className="form-error auth-error">{error}</p>}
        <div className="form-group">
          <label htmlFor="signin-email" className="form-label">Email</label>
          <input
            id="signin-email"
            type="email"
            className="form-input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
          />
        </div>
        <div className="form-group">
          <label htmlFor="signin-password" className="form-label">Password</label>
          <input
            id="signin-password"
            type="password"
            className="form-input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </div>
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </div>
      </form>
      <p className="auth-footer">
        Don&apos;t have an account? <Link to="/signup">Sign up</Link>
      </p>
    </div>
  );
}
