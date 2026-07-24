import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login, createCollection } from '../../services/api';
import { Lock, Mail, AlertCircle, Eye, EyeOff } from 'lucide-react';

const Login = ({ onLogin }) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [hasSubmitted, setHasSubmitted] = useState(false); // only show errors after first submit
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setHasSubmitted(true);

    try {
      const response = await login(email, password);
      // Save token to localStorage or context
      if (response.access_token) {
        localStorage.setItem('authToken', response.access_token);
        localStorage.setItem('userId', response.user_id);
        localStorage.setItem('userName', response.name);

      //  if (response.tokens && response.tokens.access_token) {
      //   localStorage.setItem('authToken', response.tokens.access_token);
      //   localStorage.setItem('userId', response.user_id);
      //   localStorage.setItem('userName', response.name);
        
        // Create a collection after successful login
        try {
          const collectionResponse = await createCollection();
          localStorage.setItem('collectionName', collectionResponse.collection_name);
        } catch (collectionError) {
          console.error('Failed to create collection:', collectionError);
          // Even if collection creation fails, we can still proceed with login
        }
        
        // Notify parent component
        if (onLogin) {
          onLogin();
        }
        // Redirect to main app
        navigate('/');
      } else {
        setError('Login failed. Please try again.');
      }
    } catch (err) {
      setError(err.message || 'An error occurred during login');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 px-4">
      <div className="bg-gradient-to-br from-gray-50 to-gray-100 shadow-[20px_20px_40px_#b8b9be,-20px_-20px_40px_#ffffff] rounded-3xl p-10 w-full max-w-md">
        <div className="text-center mb-8">
          {/* Logo Container - Neumorphic */}
          <div className="mx-auto h-20 w-20 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center shadow-[8px_8px_16px_#b8b9be,-4px_-4px_8px_#ffffff] mb-6">
            <Lock className="h-10 w-10 text-white" />
          </div>
          
          {/* Title */}
          <h1 className="text-4xl font-extrabold text-gray-800 mb-3">
            RAG Chatbot
          </h1>
          
          <div className="px-4">
            <p className="text-base font-semibold text-gray-700 leading-relaxed mb-2">
              RAG Powered AI Chatbot
            </p>
            <p className="text-sm text-gray-600 leading-relaxed">
              Ministry of New & Renewable Energy
            </p>
          </div>
        </div>

        {/* Error Alert - only shown after user has tried to submit */}
        {error && hasSubmitted && (
          <div className="rounded-xl bg-gradient-to-br from-red-50 to-red-100 p-4 mb-6 shadow-[inset_3px_3px_6px_rgba(220,38,38,0.2),inset_-3px_-3px_6px_rgba(255,255,255,0.8)]">
            <div className="flex items-start">
              <AlertCircle className="h-5 w-5 text-red-500 mr-3 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-red-700 font-medium">{error}</p>
            </div>
          </div>
        )}

        <form className="space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-5">
            {/* Email Input - Neumorphic */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">Email Address</label>
              <div className="relative">
                <div className="absolute left-3 top-3.5 p-1.5 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff]">
                  <Mail className="h-4 w-4 text-gray-600" />
                </div>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-14 pr-4 py-3.5 bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl shadow-[inset_3px_3px_6px_#b8b9be,inset_-3px_-3px_6px_#ffffff] focus:shadow-[inset_4px_4px_8px_#b8b9be,inset_-4px_-4px_8px_#ffffff] text-gray-900 placeholder-gray-500 transition-all duration-200 border-0 focus:outline-none"
                  placeholder="Enter your email"
                />
              </div>
            </div>

            {/* Password Input - Neumorphic */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">Password</label>
              <div className="relative">
                <div className="absolute left-3 top-3.5 p-1.5 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff]">
                  <Lock className="h-4 w-4 text-gray-600" />
                </div>
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-14 pr-14 py-3.5 bg-gradient-to-br from-gray-50 to-gray-100 rounded-xl shadow-[inset_3px_3px_6px_#b8b9be,inset_-3px_-3px_6px_#ffffff] focus:shadow-[inset_4px_4px_8px_#b8b9be,inset_-4px_-4px_8px_#ffffff] text-gray-900 placeholder-gray-500 transition-all duration-200 border-0 focus:outline-none"
                  placeholder="Enter your password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-3.5 p-1.5 rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 shadow-[2px_2px_4px_#b8b9be,-2px_-2px_4px_#ffffff] hover:shadow-[inset_2px_2px_4px_#b8b9be,inset_-2px_-2px_4px_#ffffff] text-gray-600 hover:text-gray-800 transition-all duration-200"
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
          </div>

          {/* Submit Button - Neumorphic */}
          <button
            type="submit"
            disabled={loading}
            className={`w-full py-3.5 rounded-xl font-semibold transition-all duration-200 focus:outline-none ${
              loading 
                ? 'bg-gradient-to-br from-gray-100 to-gray-200 text-gray-500 shadow-[inset_3px_3px_6px_#b8b9be,inset_-3px_-3px_6px_#ffffff] cursor-not-allowed'
                : 'bg-gradient-to-br from-blue-500 to-blue-600 text-white shadow-[6px_6px_12px_#b8b9be,-4px_-4px_8px_#ffffff] hover:shadow-[8px_8px_16px_#b8b9be,-6px_-6px_12px_#ffffff] active:shadow-[inset_3px_3px_6px_rgba(0,0,0,0.2),inset_-2px_-2px_4px_rgba(255,255,255,0.1)]'
            }`}
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>

        {/* Footer - Neumorphic divider */}
        <div className="mt-8 pt-6 relative">
          <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-gray-300 to-transparent" style={{ boxShadow: '0 1px 0 rgba(255,255,255,0.5)' }}></div>
          <p className="text-center text-xs text-gray-600">
            © {new Date().getFullYear()} RAG Chatbot | Ministry of New & Renewable Energy
          </p>
        </div>
      </div>
    </div>
  );
};

export default Login;