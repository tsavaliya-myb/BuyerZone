import React, { useState } from 'react';
import { Lock, ArrowRight, User } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { authService } from '@/services/auth';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isHovered, setIsHovered] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const data = await authService.login({ username, password });

      if (data.access_token) {
        localStorage.setItem('token', data.access_token);
        localStorage.setItem('username', username);
        if (data.name) {
          localStorage.setItem('user_name', data.name);
        } else if (data.username) {
          localStorage.setItem('user_name', data.username);
        } else if (data.user?.name) {
          localStorage.setItem('user_name', data.user.name);
        } else if (data.user?.username) {
          localStorage.setItem('user_name', data.user.username);
        }
        navigate('/');
      } else {
        setError('Login failed, no token received.');
      }
    } catch (err: any) {
      console.error('Login error:', err);
      const data = err.response?.data;
      const serverMessage = data?.detail || data?.message || data?.error || (typeof data === 'string' ? data : null);
      setError(serverMessage || 'Invalid username or password');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4 relative overflow-hidden font-sans text-slate-900">
      {/* Background Orbs */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-100/50 blur-[120px] rounded-full animate-pulse" />
      <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-indigo-100/50 blur-[120px] rounded-full animate-pulse decoration-indigo-500 delay-1000" />

      <div className="w-full max-w-[420px] relative">
        {/* Glow Effect */}
        <div className="absolute -inset-1 bg-gradient-to-r from-blue-200 to-indigo-200 rounded-[2.5rem] blur opacity-20 group-hover:opacity-40 transition duration-1000"></div>

        <div className="relative bg-white/80 backdrop-blur-2xl border border-slate-200/60 p-8 pt-10 rounded-[2.5rem] shadow-2xl">
          {/* Header */}
          <div className="mb-10 text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-2xl mb-6 shadow-lg shadow-blue-500/20 rotate-12 hover:rotate-0 transition-transform duration-500">
              <Lock className="text-white w-8 h-8" />
            </div>
            <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight mb-2">Welcome Back</h1>
            <p className="text-slate-500 text-sm font-medium">Log in to access your dashboard</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="bg-red-50 border border-red-100 text-red-600 text-sm p-3 rounded-xl text-center">
                {error}
              </div>
            )}

            <div className="space-y-4">
              {/* Username Field */}
              <div className="group relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <User className="h-5 w-5 text-slate-400 group-focus-within:text-blue-500 transition-colors" />
                </div>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Username"
                  className="block w-full pl-11 pr-4 py-4 bg-slate-50 border border-slate-200 rounded-2xl text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500/50 hover:bg-slate-100/50 transition-all outline-none"
                  required
                />
              </div>

              {/* Password Field */}
              <div className="group relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <Lock className="h-5 w-5 text-slate-400 group-focus-within:text-blue-500 transition-colors" />
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Password"
                  className="block w-full pl-11 pr-4 py-4 bg-slate-50 border border-slate-200 rounded-2xl text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500/50 hover:bg-slate-100/50 transition-all outline-none"
                  required
                />
              </div>
            </div>

            <div className="flex items-center justify-between text-xs px-1">
              <label className="flex items-center space-x-2 cursor-pointer group">
                <div className="relative flex items-center">
                  <input type="checkbox" className="peer h-4 w-4 cursor-pointer appearance-none rounded border border-slate-300 bg-white checked:bg-blue-600 checked:border-blue-600 transition-all focus:ring-2 focus:ring-blue-500/20" />
                  <svg className="absolute w-3 h-3 text-white transition-opacity opacity-0 peer-checked:opacity-100 top-0.5 left-0.5 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="4">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <span className="text-slate-500 group-hover:text-slate-700 font-medium transition-colors">Remember me</span>
              </label>
              <a href="#" className="text-blue-600 hover:text-blue-700 font-bold transition-colors">Forgot password?</a>
            </div>

            {/* Login Button */}
            <button
              disabled={isLoading}
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
              className="w-full py-4 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-2xl font-bold text-sm tracking-widest uppercase shadow-lg shadow-blue-600/20 hover:shadow-blue-600/40 transform hover:-translate-y-0.5 active:translate-y-0 transition-all duration-300 flex items-center justify-center gap-2 group disabled:opacity-70 disabled:cursor-not-allowed disabled:transform-none"
            >
              {isLoading ? 'Signing In...' : 'Sign In'}
              {!isLoading && <ArrowRight className={`w-4 h-4 transition-transform duration-300 ${isHovered ? 'translate-x-1' : ''}`} />}
            </button>
          </form>

          <p className="mt-8 text-center text-slate-500 text-sm">
            Don't have an account?{' '}
            <a href="#" className="text-blue-600 hover:text-blue-700 font-bold transition-colors underline decoration-blue-500/30 underline-offset-4 decoration-2">
              Create account
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
