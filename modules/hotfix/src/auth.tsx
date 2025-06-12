import React, { useState } from 'react';

/**
 * HOTFIX: Enhanced authentication component with security improvements
 * Version: 1.1.0
 * Date: 2024-12-08
 * 
 * Security fixes:
 * - Added input validation
 * - Improved error handling
 * - Enhanced session management
 */

interface AuthProps {
  onLogin: (token: string) => void;
  onError: (error: string) => void;
}

export const Auth: React.FC<AuthProps> = ({ onLogin, onError }) => {
  const [pin, setPin] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const validatePin = (pin: string): boolean => {
    // Enhanced validation
    if (!pin || pin.length < 4) {
      return false;
    }
    
    // Check for common weak patterns
    if (/^(\d)\1+$/.test(pin)) { // All same digits
      return false;
    }
    
    return true;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validatePin(pin)) {
      onError('Invalid PIN format');
      return;
    }

    setIsLoading(true);
    
    try {
      const response = await fetch('/api/validatePin', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ pin }),
      });

      if (!response.ok) {
        throw new Error('Authentication failed');
      }

      const data = await response.json();
      
      if (data.success && data.token) {
        onLogin(data.token);
      } else {
        onError(data.message || 'Authentication failed');
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Network error');
    } finally {
      setIsLoading(false);
      setPin(''); // Clear PIN for security
    }
  };

  return (
    <form onSubmit={handleSubmit} className="auth-form">
      <div className="form-group">
        <label htmlFor="pin">Enter PIN:</label>
        <input
          id="pin"
          type="password"
          value={pin}
          onChange={(e) => setPin(e.target.value)}
          disabled={isLoading}
          maxLength={8}
          autoComplete="current-password"
          required
        />
      </div>
      
      <button 
        type="submit" 
        disabled={isLoading || !validatePin(pin)}
        className="auth-submit"
      >
        {isLoading ? 'Authenticating...' : 'Login'}
      </button>
    </form>
  );
}; 