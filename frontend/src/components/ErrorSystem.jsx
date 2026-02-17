/**
 * ====================================================================
 * SEVA SETU BOT - ERROR BOUNDARY & AUTO-RECOVERY SYSTEM
 * Self-healing error handling with admin notifications
 * ====================================================================
 */

import React, { Component, createContext, useContext, useState, useCallback, useEffect } from 'react';
import { AlertTriangle, RefreshCw, Send, XCircle, CheckCircle } from 'lucide-react';
import axios from 'axios';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Error Context for global error state management
const ErrorContext = createContext(null);

export const useError = () => {
  const context = useContext(ErrorContext);
  if (!context) {
    throw new Error('useError must be used within an ErrorProvider');
  }
  return context;
};

// Error types for categorization
export const ERROR_TYPES = {
  NETWORK: 'network',
  API: 'api',
  VALIDATION: 'validation',
  AUTH: 'auth',
  TIMEOUT: 'timeout',
  UNKNOWN: 'unknown',
  BOT_STUCK: 'bot_stuck',
  RATE_LIMIT: 'rate_limit',
};

// Error severity levels
export const ERROR_SEVERITY = {
  LOW: 'low',
  MEDIUM: 'medium',
  HIGH: 'high',
  CRITICAL: 'critical',
};

// Error messages with recovery suggestions
const ERROR_MESSAGES = {
  [ERROR_TYPES.NETWORK]: {
    title: 'Connection Lost',
    message: 'Unable to connect to our servers.',
    recovery: [
      'Check your internet connection',
      'Try refreshing the page',
      'Wait a moment and try again',
    ],
  },
  [ERROR_TYPES.API]: {
    title: 'Service Unavailable',
    message: 'Our service is temporarily unavailable.',
    recovery: [
      'Please wait a moment and try again',
      'If the problem persists, contact support',
    ],
  },
  [ERROR_TYPES.TIMEOUT]: {
    title: 'Request Timeout',
    message: 'The request is taking longer than expected.',
    recovery: [
      'Your request may still be processing',
      'Wait a few seconds before retrying',
      'Try with a shorter message',
    ],
  },
  [ERROR_TYPES.BOT_STUCK]: {
    title: 'Bot Not Responding',
    message: 'The assistant seems to be stuck.',
    recovery: [
      'Restarting the conversation...',
      'Your previous messages are saved',
    ],
  },
  [ERROR_TYPES.RATE_LIMIT]: {
    title: 'Too Many Requests',
    message: 'You\'re sending messages too quickly.',
    recovery: [
      'Please wait a moment before sending another message',
      'Try again in 30 seconds',
    ],
  },
  [ERROR_TYPES.AUTH]: {
    title: 'Session Expired',
    message: 'Your session has expired.',
    recovery: [
      'Please refresh the page',
      'You may need to log in again',
    ],
  },
  [ERROR_TYPES.UNKNOWN]: {
    title: 'Something Went Wrong',
    message: 'An unexpected error occurred.',
    recovery: [
      'Try refreshing the page',
      'Clear your browser cache',
      'Contact support if the issue persists',
    ],
  },
};

// Send error report to admin
const sendErrorReport = async (error, context = {}) => {
  try {
    await axios.post(`${API}/admin/error-report`, {
      error_type: error.type || ERROR_TYPES.UNKNOWN,
      error_message: error.message,
      stack_trace: error.stack,
      context: {
        url: window.location.href,
        userAgent: navigator.userAgent,
        timestamp: new Date().toISOString(),
        ...context,
      },
      severity: error.severity || ERROR_SEVERITY.MEDIUM,
    });
    console.log('[ErrorSystem] Error report sent to admin');
  } catch (e) {
    console.error('[ErrorSystem] Failed to send error report:', e);
  }
};

// Error Provider Component
export const ErrorProvider = ({ children }) => {
  const [errors, setErrors] = useState([]);
  const [isRecovering, setIsRecovering] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const [lastErrorTime, setLastErrorTime] = useState(null);
  
  // Add error to stack
  const addError = useCallback((error) => {
    const errorObj = {
      id: Date.now(),
      type: error.type || ERROR_TYPES.UNKNOWN,
      message: error.message,
      severity: error.severity || ERROR_SEVERITY.MEDIUM,
      timestamp: new Date().toISOString(),
      context: error.context || {},
      ...ERROR_MESSAGES[error.type || ERROR_TYPES.UNKNOWN],
    };
    
    setErrors(prev => [...prev, errorObj]);
    setLastErrorTime(Date.now());
    
    // Send critical errors to admin
    if (error.severity === ERROR_SEVERITY.CRITICAL || error.severity === ERROR_SEVERITY.HIGH) {
      sendErrorReport(errorObj, error.context);
    }
    
    return errorObj.id;
  }, []);
  
  // Clear specific error
  const clearError = useCallback((errorId) => {
    setErrors(prev => prev.filter(e => e.id !== errorId));
  }, []);
  
  // Clear all errors
  const clearAllErrors = useCallback(() => {
    setErrors([]);
  }, []);
  
  // Auto-recovery mechanism
  const attemptRecovery = useCallback(async (recoveryFn) => {
    if (isRecovering) return false;
    
    setIsRecovering(true);
    setRetryCount(prev => prev + 1);
    
    try {
      await recoveryFn();
      setRetryCount(0);
      clearAllErrors();
      return true;
    } catch (e) {
      if (retryCount >= 3) {
        // After 3 retries, notify admin and show critical error
        addError({
          type: ERROR_TYPES.BOT_STUCK,
          message: 'Auto-recovery failed after multiple attempts',
          severity: ERROR_SEVERITY.CRITICAL,
          context: { retryCount },
        });
      }
      return false;
    } finally {
      setIsRecovering(false);
    }
  }, [isRecovering, retryCount, addError, clearAllErrors]);
  
  // Detect if bot is stuck (no response for 30 seconds)
  const checkBotHealth = useCallback((lastResponseTime) => {
    if (!lastResponseTime) return true;
    
    const timeSinceLastResponse = Date.now() - lastResponseTime;
    if (timeSinceLastResponse > 30000) {
      addError({
        type: ERROR_TYPES.BOT_STUCK,
        message: 'Bot has not responded for 30 seconds',
        severity: ERROR_SEVERITY.HIGH,
      });
      return false;
    }
    return true;
  }, [addError]);
  
  const value = {
    errors,
    addError,
    clearError,
    clearAllErrors,
    isRecovering,
    attemptRecovery,
    retryCount,
    checkBotHealth,
    lastErrorTime,
  };
  
  return (
    <ErrorContext.Provider value={value}>
      {children}
    </ErrorContext.Provider>
  );
};

// Error Boundary Component (Class-based for catching render errors)
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { 
      hasError: false, 
      error: null, 
      errorInfo: null,
      isRecovering: false,
    };
  }
  
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  
  componentDidCatch(error, errorInfo) {
    this.setState({ errorInfo });
    
    // Send error report to admin
    sendErrorReport({
      type: ERROR_TYPES.UNKNOWN,
      message: error.message,
      stack: error.stack,
      severity: ERROR_SEVERITY.CRITICAL,
    }, {
      componentStack: errorInfo?.componentStack,
    });
    
    console.error('[ErrorBoundary] Caught error:', error, errorInfo);
  }
  
  handleRecover = () => {
    this.setState({ isRecovering: true });
    
    setTimeout(() => {
      this.setState({ 
        hasError: false, 
        error: null, 
        errorInfo: null,
        isRecovering: false,
      });
    }, 1000);
  };
  
  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-red-50 to-orange-50 p-6">
          <div className="max-w-md w-full bg-white rounded-2xl shadow-xl p-8 text-center">
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-6">
              <XCircle className="w-8 h-8 text-red-600" />
            </div>
            
            <h1 className="text-2xl font-bold text-gray-900 mb-2">
              Something Went Wrong
            </h1>
            <p className="text-gray-600 mb-6">
              We apologize for the inconvenience. The application encountered an unexpected error.
            </p>
            
            <div className="bg-red-50 rounded-lg p-4 mb-6 text-left">
              <p className="text-sm font-medium text-red-800 mb-2">Error Details:</p>
              <p className="text-xs text-red-600 font-mono overflow-auto max-h-24">
                {this.state.error?.message || 'Unknown error'}
              </p>
            </div>
            
            <div className="space-y-3">
              <button
                onClick={this.handleRecover}
                disabled={this.state.isRecovering}
                className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded-lg transition-colors disabled:opacity-50"
              >
                {this.state.isRecovering ? (
                  <>
                    <RefreshCw className="w-5 h-5 animate-spin" />
                    Recovering...
                  </>
                ) : (
                  <>
                    <RefreshCw className="w-5 h-5" />
                    Try Again
                  </>
                )}
              </button>
              
              <button
                onClick={() => window.location.reload()}
                className="w-full flex items-center justify-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 font-semibold py-3 px-6 rounded-lg transition-colors"
              >
                Refresh Page
              </button>
            </div>
            
            <p className="text-xs text-gray-500 mt-6">
              An error report has been automatically sent to our team.
            </p>
          </div>
        </div>
      );
    }
    
    return this.props.children;
  }
}

// Error Toast Component for inline errors
export const ErrorToast = ({ error, onDismiss, onRetry }) => {
  const [isVisible, setIsVisible] = useState(true);
  
  useEffect(() => {
    const timer = setTimeout(() => {
      if (error.severity !== ERROR_SEVERITY.CRITICAL) {
        setIsVisible(false);
        setTimeout(onDismiss, 300);
      }
    }, 10000);
    
    return () => clearTimeout(timer);
  }, [error, onDismiss]);
  
  const severityStyles = {
    [ERROR_SEVERITY.LOW]: 'bg-blue-50 border-blue-200 text-blue-800',
    [ERROR_SEVERITY.MEDIUM]: 'bg-yellow-50 border-yellow-200 text-yellow-800',
    [ERROR_SEVERITY.HIGH]: 'bg-orange-50 border-orange-200 text-orange-800',
    [ERROR_SEVERITY.CRITICAL]: 'bg-red-50 border-red-200 text-red-800',
  };
  
  return (
    <div
      className={`fixed bottom-4 right-4 max-w-md transform transition-all duration-300 z-50 ${
        isVisible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'
      }`}
    >
      <div className={`rounded-lg border-l-4 p-4 shadow-lg ${severityStyles[error.severity]}`}>
        <div className="flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="font-semibold">{error.title}</h4>
            <p className="text-sm mt-1">{error.message}</p>
            
            {error.recovery && error.recovery.length > 0 && (
              <ul className="text-xs mt-2 space-y-1">
                {error.recovery.map((step, i) => (
                  <li key={i}>• {step}</li>
                ))}
              </ul>
            )}
            
            <div className="flex gap-2 mt-3">
              {onRetry && (
                <button
                  onClick={onRetry}
                  className="text-xs font-semibold bg-white/50 hover:bg-white px-3 py-1.5 rounded transition-colors flex items-center gap-1"
                >
                  <RefreshCw className="w-3 h-3" />
                  Retry
                </button>
              )}
              <button
                onClick={onDismiss}
                className="text-xs font-semibold bg-white/50 hover:bg-white px-3 py-1.5 rounded transition-colors"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Hook for API calls with automatic error handling
export const useApiWithRecovery = () => {
  const { addError, attemptRecovery } = useError();
  const [isLoading, setIsLoading] = useState(false);
  
  const callApi = useCallback(async (apiCall, options = {}) => {
    const { 
      retries = 3, 
      retryDelay = 1000, 
      onSuccess, 
      onError,
      errorType = ERROR_TYPES.API,
    } = options;
    
    setIsLoading(true);
    let lastError = null;
    
    for (let attempt = 0; attempt < retries; attempt++) {
      try {
        const result = await apiCall();
        setIsLoading(false);
        onSuccess?.(result);
        return result;
      } catch (error) {
        lastError = error;
        
        // Categorize error
        let type = errorType;
        if (error.code === 'ERR_NETWORK' || error.message?.includes('Network')) {
          type = ERROR_TYPES.NETWORK;
        } else if (error.response?.status === 429) {
          type = ERROR_TYPES.RATE_LIMIT;
        } else if (error.response?.status === 401 || error.response?.status === 403) {
          type = ERROR_TYPES.AUTH;
        } else if (error.code === 'ECONNABORTED') {
          type = ERROR_TYPES.TIMEOUT;
        }
        
        // Last attempt - show error
        if (attempt === retries - 1) {
          const severity = type === ERROR_TYPES.AUTH ? ERROR_SEVERITY.HIGH : ERROR_SEVERITY.MEDIUM;
          addError({ type, message: error.message, severity });
          onError?.(error);
        } else {
          // Wait before retry with exponential backoff
          await new Promise(resolve => setTimeout(resolve, retryDelay * (attempt + 1)));
        }
      }
    }
    
    setIsLoading(false);
    throw lastError;
  }, [addError]);
  
  return { callApi, isLoading };
};

export default {
  ErrorProvider,
  ErrorBoundary,
  ErrorToast,
  useError,
  useApiWithRecovery,
  ERROR_TYPES,
  ERROR_SEVERITY,
};
