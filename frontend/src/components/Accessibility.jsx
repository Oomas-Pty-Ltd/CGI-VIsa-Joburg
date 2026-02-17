/**
 * ====================================================================
 * SEVA SETU BOT - ACCESSIBILITY COMPONENTS
 * WCAG 2.1 AA Compliant Reusable Components
 * ====================================================================
 */

import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, CheckCircle, AlertTriangle, Info, X } from 'lucide-react';

/**
 * Skip Link - For keyboard navigation
 */
export const SkipLink = ({ targetId = "main-content", children = "Skip to main content" }) => (
  <a 
    href={`#${targetId}`} 
    className="skip-link"
    tabIndex={0}
  >
    {children}
  </a>
);

/**
 * Screen Reader Only Text
 */
export const SROnly = ({ children }) => (
  <span className="sr-only">{children}</span>
);

/**
 * Live Region - Announces dynamic content to screen readers
 */
export const LiveRegion = ({ 
  children, 
  type = "polite", // polite, assertive, off
  atomic = true,
  relevant = "additions text"
}) => (
  <div 
    aria-live={type}
    aria-atomic={atomic}
    aria-relevant={relevant}
    className="sr-only"
  >
    {children}
  </div>
);

/**
 * Accessible Error Message with Recovery Steps
 */
export const ErrorMessage = ({ 
  title = "Error", 
  message, 
  recoverySteps = [],
  onDismiss,
  id 
}) => (
  <div 
    role="alert"
    aria-labelledby={`${id}-title`}
    aria-describedby={`${id}-desc`}
    className="error-message"
  >
    <AlertCircle className="error-message-icon flex-shrink-0" aria-hidden="true" />
    <div className="error-message-content">
      <div id={`${id}-title`} className="error-message-title">{title}</div>
      <div id={`${id}-desc`}>{message}</div>
      {recoverySteps.length > 0 && (
        <div className="error-message-recovery mt-2">
          <strong>How to fix:</strong>
          <ul className="list-disc pl-5 mt-1">
            {recoverySteps.map((step, i) => (
              <li key={i}>{step}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
    {onDismiss && (
      <button 
        onClick={onDismiss}
        aria-label="Dismiss error"
        className="ml-2 p-1 hover:bg-red-100 rounded"
      >
        <X size={16} aria-hidden="true" />
      </button>
    )}
  </div>
);

/**
 * Accessible Success Message
 */
export const SuccessMessage = ({ title = "Success", message, onDismiss, id }) => (
  <div 
    role="status"
    aria-labelledby={`${id}-title`}
    className="success-message"
  >
    <CheckCircle className="flex-shrink-0 w-5 h-5" aria-hidden="true" />
    <div className="flex-1">
      <div id={`${id}-title`} className="font-semibold">{title}</div>
      <div>{message}</div>
    </div>
    {onDismiss && (
      <button 
        onClick={onDismiss}
        aria-label="Dismiss message"
        className="ml-2 p-1 hover:bg-green-100 rounded"
      >
        <X size={16} aria-hidden="true" />
      </button>
    )}
  </div>
);

/**
 * Accessible Warning Message
 */
export const WarningMessage = ({ title = "Warning", message, id }) => (
  <div 
    role="alert"
    aria-labelledby={`${id}-title`}
    className="warning-message"
  >
    <AlertTriangle className="flex-shrink-0 w-5 h-5" aria-hidden="true" />
    <div className="flex-1">
      <div id={`${id}-title`} className="font-semibold">{title}</div>
      <div>{message}</div>
    </div>
  </div>
);

/**
 * Accessible Info Message
 */
export const InfoMessage = ({ title = "Information", message, id }) => (
  <div 
    role="note"
    aria-labelledby={`${id}-title`}
    className="info-message"
  >
    <Info className="flex-shrink-0 w-5 h-5" aria-hidden="true" />
    <div className="flex-1">
      <div id={`${id}-title`} className="font-semibold">{title}</div>
      <div>{message}</div>
    </div>
  </div>
);

/**
 * Accessible Form Field with Label
 */
export const FormField = ({
  label,
  id,
  required = false,
  error = null,
  hint = null,
  children
}) => {
  const errorId = `${id}-error`;
  const hintId = `${id}-hint`;
  
  return (
    <div className="form-group mb-4">
      <label 
        htmlFor={id}
        className="block font-medium mb-1.5 text-gray-900"
        data-required={required || undefined}
      >
        {label}
        {required && <span className="text-red-600 ml-1" aria-hidden="true">*</span>}
      </label>
      
      {hint && (
        <p id={hintId} className="text-sm text-gray-500 mb-1.5">
          {hint}
        </p>
      )}
      
      {React.cloneElement(children, {
        id,
        'aria-invalid': error ? 'true' : undefined,
        'aria-describedby': [
          hint ? hintId : null,
          error ? errorId : null
        ].filter(Boolean).join(' ') || undefined,
        'aria-required': required || undefined,
        className: `${children.props.className || ''} ${error ? 'input-error' : ''}`
      })}
      
      {error && (
        <p id={errorId} className="text-sm text-red-600 mt-1.5 flex items-center gap-1">
          <AlertCircle size={14} aria-hidden="true" />
          {error}
        </p>
      )}
    </div>
  );
};

/**
 * Loading Spinner with Announcement
 */
export const LoadingSpinner = ({ 
  size = "md", 
  label = "Loading",
  fullScreen = false 
}) => {
  const sizes = {
    sm: "w-4 h-4 border-2",
    md: "w-6 h-6 border-2",
    lg: "w-8 h-8 border-3",
    xl: "w-12 h-12 border-4"
  };
  
  const spinner = (
    <div className="flex flex-col items-center gap-3" role="status" aria-live="polite">
      <div 
        className={`${sizes[size]} border-gray-200 border-t-orange-500 rounded-full animate-spin`}
        aria-hidden="true"
      />
      <span className="sr-only">{label}</span>
      {fullScreen && <span className="text-gray-600 font-medium">{label}</span>}
    </div>
  );
  
  if (fullScreen) {
    return (
      <div className="loading-overlay">
        {spinner}
      </div>
    );
  }
  
  return spinner;
};

/**
 * Accessible Button with Loading State
 */
export const AccessibleButton = ({
  children,
  loading = false,
  loadingText = "Loading...",
  disabled = false,
  variant = "primary",
  iconOnly = false,
  'aria-label': ariaLabel,
  ...props
}) => {
  const variants = {
    primary: "bg-orange-600 hover:bg-orange-700 text-white",
    secondary: "bg-white border-2 border-gray-800 text-gray-800 hover:bg-gray-800 hover:text-white",
    danger: "bg-red-600 hover:bg-red-700 text-white",
    ghost: "bg-transparent hover:bg-gray-100 text-gray-700"
  };
  
  return (
    <button
      className={`btn ${variants[variant]} ${iconOnly ? 'btn-icon' : ''} ${disabled || loading ? 'opacity-60 cursor-not-allowed' : ''}`}
      disabled={disabled || loading}
      aria-label={ariaLabel}
      aria-busy={loading}
      aria-disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <>
          <LoadingSpinner size="sm" />
          <span className={iconOnly ? 'sr-only' : ''}>{loadingText}</span>
        </>
      ) : (
        children
      )}
    </button>
  );
};

/**
 * Progress Stepper with ARIA
 */
export const ProgressStepper = ({ steps, currentStep, onStepClick }) => {
  return (
    <nav aria-label="Progress" className="stepper">
      <ol className="flex items-center gap-2">
        {steps.map((step, index) => {
          const isCompleted = index < currentStep;
          const isCurrent = index === currentStep;
          const status = isCompleted ? 'completed' : isCurrent ? 'current' : 'upcoming';
          
          return (
            <li key={step.id} className="flex items-center">
              <div 
                className="stepper-step"
                data-status={status}
              >
                <button
                  onClick={() => onStepClick && onStepClick(index)}
                  disabled={!onStepClick || (!isCompleted && !isCurrent)}
                  className="stepper-circle"
                  aria-current={isCurrent ? 'step' : undefined}
                  aria-label={`${step.label}${isCompleted ? ', completed' : isCurrent ? ', current step' : ''}`}
                >
                  {isCompleted ? (
                    <CheckCircle size={20} aria-hidden="true" />
                  ) : (
                    <span aria-hidden="true">{index + 1}</span>
                  )}
                </button>
                <span className="stepper-label">{step.label}</span>
              </div>
              
              {index < steps.length - 1 && (
                <div 
                  className="stepper-connector mx-2" 
                  data-completed={isCompleted}
                  aria-hidden="true"
                />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
};

/**
 * Focus Trap - For Modals
 */
export const useFocusTrap = (isActive) => {
  const containerRef = useRef(null);
  
  useEffect(() => {
    if (!isActive || !containerRef.current) return;
    
    const container = containerRef.current;
    const focusableElements = container.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];
    
    const handleKeyDown = (e) => {
      if (e.key !== 'Tab') return;
      
      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };
    
    container.addEventListener('keydown', handleKeyDown);
    firstElement?.focus();
    
    return () => container.removeEventListener('keydown', handleKeyDown);
  }, [isActive]);
  
  return containerRef;
};

/**
 * Announce to Screen Readers
 */
export const useAnnounce = () => {
  const [announcement, setAnnouncement] = useState('');
  
  const announce = (message, priority = 'polite') => {
    setAnnouncement('');
    setTimeout(() => setAnnouncement(message), 100);
  };
  
  const Announcer = () => (
    <LiveRegion type="assertive">{announcement}</LiveRegion>
  );
  
  return { announce, Announcer };
};

/**
 * Accessible Modal/Dialog
 */
export const AccessibleDialog = ({ 
  isOpen, 
  onClose, 
  title, 
  children,
  describedBy 
}) => {
  const containerRef = useFocusTrap(isOpen);
  
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      const handleEscape = (e) => {
        if (e.key === 'Escape') onClose();
      };
      document.addEventListener('keydown', handleEscape);
      return () => {
        document.body.style.overflow = '';
        document.removeEventListener('keydown', handleEscape);
      };
    }
  }, [isOpen, onClose]);
  
  if (!isOpen) return null;
  
  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="presentation"
    >
      <div 
        className="fixed inset-0 bg-black/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby={describedBy}
        className="relative bg-white rounded-xl shadow-xl max-w-lg w-full max-h-[90vh] overflow-auto"
      >
        <div className="flex items-center justify-between p-4 border-b">
          <h2 id="dialog-title" className="text-xl font-semibold">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="p-2 hover:bg-gray-100 rounded-full"
          >
            <X size={20} aria-hidden="true" />
          </button>
        </div>
        <div className="p-4">
          {children}
        </div>
      </div>
    </div>
  );
};

export default {
  SkipLink,
  SROnly,
  LiveRegion,
  ErrorMessage,
  SuccessMessage,
  WarningMessage,
  InfoMessage,
  FormField,
  LoadingSpinner,
  AccessibleButton,
  ProgressStepper,
  useFocusTrap,
  useAnnounce,
  AccessibleDialog
};
