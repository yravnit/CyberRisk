import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Shield } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { ThemeToggle } from '../components/ui/ThemeToggle';
import { useAuth } from '../context/AuthContext';

const inputClass =
  'w-full rounded-full border border-th-border bg-th-bg px-4 py-2.5 text-sm text-th-text-primary placeholder-th-text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-th-accent';

export const LoginPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login, register } = useAuth();

  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const from = location.state?.from || '/';

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      if (mode === 'login') {
        await login(username.trim(), password);
      } else {
        await register(username.trim(), password);
      }
      navigate(from, { replace: true });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Something went wrong. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const switchMode = () => {
    setMode((m) => (m === 'login' ? 'register' : 'login'));
    setError('');
  };

  return (
    <div className="min-h-screen flex flex-col font-sans theme-transition bg-th-bg">
      <header className="sticky top-0 z-40 w-full border-b border-th-border bg-th-surface/95 backdrop-blur-md">
        <div className="px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-th-brand flex items-center justify-center text-white shadow-soft">
              <Shield className="w-4 h-4" />
            </div>
            <span className="text-lg font-semibold text-th-text-primary font-serif tracking-tight">
              CyberRisk
            </span>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <Card className="w-full max-w-md" elevated>
          <CardHeader>
            <CardTitle>{mode === 'login' ? 'Sign in' : 'Create an account'}</CardTitle>
            <p className="text-sm text-th-text-secondary mt-1">
              {mode === 'login'
                ? 'Access your organization’s quantified risk dashboard.'
                : 'Register to quantify your own datasets. Minimum 8-character password.'}
            </p>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-1.5">
                <label htmlFor="username" className="block text-sm font-medium text-th-text-primary">
                  Username
                </label>
                <input
                  id="username"
                  className={inputClass}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="analyst@company"
                  autoComplete="username"
                  required
                  minLength={3}
                  maxLength={64}
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="password" className="block text-sm font-medium text-th-text-primary">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  className={inputClass}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  required
                  minLength={8}
                />
              </div>

              {error && (
                <p role="alert" className="text-sm text-th-danger">
                  {error}
                </p>
              )}

              <Button type="submit" className="w-full" isLoading={isSubmitting}>
                {mode === 'login' ? 'Sign in' : 'Create account'}
              </Button>
            </form>

            <button
              type="button"
              onClick={switchMode}
              className="mt-4 w-full text-center text-sm text-th-text-secondary hover:text-th-text-primary underline underline-offset-4"
            >
              {mode === 'login'
                ? 'No account? Create one'
                : 'Already registered? Sign in'}
            </button>
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

export default LoginPage;
