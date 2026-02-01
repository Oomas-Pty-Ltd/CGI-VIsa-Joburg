import React, { useState, useEffect } from 'react';
import { Button } from '../components/ui/button';
import { X } from 'lucide-react';

export default function ConsentBanner({ onAccept, onDecline }) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Check if consent was already given
    const consent = localStorage.getItem('cookie_consent');
    if (!consent) {
      setIsVisible(true);
    }
  }, []);

  const handleAccept = () => {
    localStorage.setItem('cookie_consent', JSON.stringify({
      accepted: true,
      timestamp: new Date().toISOString(),
      preferences: {
        necessary: true,
        analytics: true,
        marketing: false
      }
    }));
    setIsVisible(false);
    if (onAccept) onAccept();
  };

  const handleDecline = () => {
    localStorage.setItem('cookie_consent', JSON.stringify({
      accepted: false,
      timestamp: new Date().toISOString(),
      preferences: {
        necessary: true,
        analytics: false,
        marketing: false
      }
    }));
    setIsVisible(false);
    if (onDecline) onDecline();
  };

  const handleCustomize = () => {
    // For now, just accept necessary cookies
    localStorage.setItem('cookie_consent', JSON.stringify({
      accepted: true,
      timestamp: new Date().toISOString(),
      preferences: {
        necessary: true,
        analytics: false,
        marketing: false
      }
    }));
    setIsVisible(false);
  };

  if (!isVisible) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 p-4 bg-gradient-to-r from-gray-900 to-gray-800 border-t border-gray-700 shadow-2xl">
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          {/* Content */}
          <div className="flex-1">
            <div className="flex items-start gap-3">
              <div className="text-2xl">🍪</div>
              <div>
                <h3 className="text-white font-semibold text-lg mb-1">
                  Cookie & Privacy Consent
                </h3>
                <p className="text-gray-300 text-sm leading-relaxed">
                  We use cookies and similar technologies to enhance your experience, analyze usage, and personalize content. 
                  By clicking "Accept All", you consent to our use of cookies as described in our{' '}
                  <a href="/privacy" className="text-[#E06F2C] hover:underline">Privacy Policy</a>.
                  This site complies with <span className="font-medium">GDPR</span>, <span className="font-medium">POPIA</span>, and <span className="font-medium">DPDA</span> regulations.
                </p>
                <p className="text-gray-400 text-xs mt-2">
                  ⚠️ Necessary cookies are always active for essential functionality.
                </p>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-3 ml-0 md:ml-4">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCustomize}
              className="text-gray-300 border-gray-600 hover:bg-gray-700 hover:text-white"
            >
              Customize
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDecline}
              className="text-gray-300 border-gray-600 hover:bg-gray-700 hover:text-white"
            >
              Decline Optional
            </Button>
            <Button
              size="sm"
              onClick={handleAccept}
              className="bg-[#2E8B57] hover:bg-[#246b45] text-white px-6"
            >
              Accept All
            </Button>
          </div>

          {/* Close button */}
          <button
            onClick={handleDecline}
            className="absolute top-2 right-2 md:hidden text-gray-400 hover:text-white"
          >
            <X size={20} />
          </button>
        </div>

        {/* Compliance badges */}
        <div className="flex items-center gap-4 mt-3 pt-3 border-t border-gray-700">
          <span className="text-xs text-gray-500 flex items-center gap-1">
            <span className="w-2 h-2 bg-green-500 rounded-full"></span>
            GDPR Compliant
          </span>
          <span className="text-xs text-gray-500 flex items-center gap-1">
            <span className="w-2 h-2 bg-green-500 rounded-full"></span>
            POPIA Compliant
          </span>
          <span className="text-xs text-gray-500 flex items-center gap-1">
            <span className="w-2 h-2 bg-green-500 rounded-full"></span>
            DPDA Compliant
          </span>
        </div>
      </div>
    </div>
  );
}
