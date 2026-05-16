import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { exchangeCodeForTokens } from '../lib/cognito';
import { useAuth } from '../contexts/AuthContext';

export function CallbackPage() {
  const { setTokens } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;
    done.current = true;

    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');
    const errParam = params.get('error');

    if (errParam) {
      setError(`Cognito error: ${errParam} — ${params.get('error_description') ?? ''}`);
      return;
    }

    if (!code || !state) {
      setError('Missing code or state in callback URL.');
      return;
    }

    exchangeCodeForTokens(code, state)
      .then(({ id_token, refresh_token }) => {
        setTokens(id_token, refresh_token);
        navigate('/', { replace: true });
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Authentication failed.');
      });
  }, [navigate, setTokens]);

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-700 to-blue-900 p-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl text-center">
          <p className="text-sm font-semibold text-red-600 mb-4">Sign-in failed</p>
          <p className="text-sm text-gray-500 mb-6">{error}</p>
          <button
            onClick={() => navigate('/login', { replace: true })}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
          >
            Back to login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen items-center justify-center bg-gradient-to-br from-blue-700 to-blue-900">
      <div className="text-center text-white space-y-3">
        <div className="h-10 w-10 mx-auto animate-spin rounded-full border-4 border-white border-t-transparent" />
        <p className="text-sm font-medium">Completing sign-in…</p>
      </div>
    </div>
  );
}
