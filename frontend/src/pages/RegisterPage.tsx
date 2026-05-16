import { useNavigate } from 'react-router-dom';
import { IS_HOSTED_UI, redirectToSignUp } from '../lib/cognito';

export function RegisterPage() {
  const navigate = useNavigate();

  if (IS_HOSTED_UI) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-700 to-blue-900 p-4">
        <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl text-center">
          <h1 className="mb-1 text-2xl font-bold text-gray-900">AeroLink</h1>
          <p className="mb-6 text-sm text-gray-500">Create your account</p>
          <button
            onClick={redirectToSignUp}
            className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            Create account with Google
          </button>
          <button
            onClick={() => navigate('/login')}
            className="mt-3 w-full rounded-lg border border-gray-300 py-2.5 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Back to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-700 to-blue-900 p-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl text-center">
        <h1 className="mb-1 text-2xl font-bold text-gray-900">AeroLink</h1>
        <p className="mb-4 text-sm text-gray-500">
          In local dev, create users via the LocalStack Cognito CLI:
        </p>
        <pre className="mb-6 rounded-lg bg-gray-50 p-3 text-left text-xs text-gray-700 overflow-x-auto">
          {`docker-compose exec localstack awslocal \\
  cognito-idp admin-create-user \\
  --user-pool-id <POOL_ID> \\
  --username myuser \\
  --user-attributes \\
    Name=email,Value=me@test.com \\
    Name=email_verified,Value=true \\
  --temporary-password Temp1234!`}
        </pre>
        <button
          onClick={() => navigate('/login')}
          className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
        >
          Back to sign in
        </button>
      </div>
    </div>
  );
}
