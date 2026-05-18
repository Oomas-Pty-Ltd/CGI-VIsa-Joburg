/**
 * ====================================================================
 * SEVA SETU BOT - DYNAMIC THEME SYSTEM
 * Google AI-Inspired Design with Context-Aware Theming
 * ====================================================================
 */

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

// Theme configurations inspired by Google's Material Design 3 & Gemini
const THEMES = {
  default: {
    name: 'Default',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    backgroundAlt: 'linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%)',
    primary: '#4285F4',
    primaryDark: '#1967D2',
    secondary: '#34A853',
    accent: '#FBBC04',
    surface: 'rgba(255, 255, 255, 0.95)',
    surfaceVariant: 'rgba(255, 255, 255, 0.7)',
    text: '#202124',
    textSecondary: '#5F6368',
    chatBubbleUser: '#4285F4',
    chatBubbleBot: '#F8F9FA',
    statusIndicator: '#34A853',
    particles: ['#4285F4', '#34A853', '#FBBC04', '#EA4335'],
  },
  
  welcome: {
    name: 'Welcome',
    background: 'linear-gradient(135deg, #FF6B35 0%, #F7C59F 50%, #EFEFD0 100%)',
    backgroundAlt: 'linear-gradient(135deg, #FFF9E6 0%, #FFE4C4 100%)',
    primary: '#FF6B35',
    primaryDark: '#E55A2B',
    secondary: '#2E8B57',
    accent: '#FFD700',
    surface: 'rgba(255, 255, 255, 0.98)',
    surfaceVariant: 'rgba(255, 249, 230, 0.9)',
    text: '#1A2E40',
    textSecondary: '#5D4E37',
    chatBubbleUser: '#FF6B35',
    chatBubbleBot: '#FFF9E6',
    statusIndicator: '#2E8B57',
    particles: ['#FF6B35', '#FFD700', '#2E8B57', '#F7C59F'],
  },
  
  passport: {
    name: 'Passport Services',
    background: 'linear-gradient(135deg, #1A2E40 0%, #2D4A5E 50%, #3D6B7D 100%)',
    backgroundAlt: 'linear-gradient(135deg, #E8F4F8 0%, #D1E8E2 100%)',
    primary: '#1A2E40',
    primaryDark: '#0F1C28',
    secondary: '#FF6B35',
    accent: '#4ECDC4',
    surface: 'rgba(255, 255, 255, 0.98)',
    surfaceVariant: 'rgba(232, 244, 248, 0.95)',
    text: '#1A2E40',
    textSecondary: '#4A6572',
    chatBubbleUser: '#1A2E40',
    chatBubbleBot: '#E8F4F8',
    statusIndicator: '#4ECDC4',
    particles: ['#1A2E40', '#4ECDC4', '#FF6B35', '#2D4A5E'],
  },
  
  visa: {
    name: 'Visa Services',
    background: 'linear-gradient(135deg, #6366F1 0%, #8B5CF6 50%, #A78BFA 100%)',
    backgroundAlt: 'linear-gradient(135deg, #F5F3FF 0%, #EDE9FE 100%)',
    primary: '#6366F1',
    primaryDark: '#4F46E5',
    secondary: '#10B981',
    accent: '#F59E0B',
    surface: 'rgba(255, 255, 255, 0.98)',
    surfaceVariant: 'rgba(245, 243, 255, 0.95)',
    text: '#1E1B4B',
    textSecondary: '#4C4679',
    chatBubbleUser: '#6366F1',
    chatBubbleBot: '#F5F3FF',
    statusIndicator: '#10B981',
    particles: ['#6366F1', '#8B5CF6', '#10B981', '#F59E0B'],
  },
  
  emergency: {
    name: 'Emergency',
    background: 'linear-gradient(135deg, #DC2626 0%, #EF4444 50%, #F87171 100%)',
    backgroundAlt: 'linear-gradient(135deg, #FEF2F2 0%, #FEE2E2 100%)',
    primary: '#DC2626',
    primaryDark: '#B91C1C',
    secondary: '#1A2E40',
    accent: '#FBBF24',
    surface: 'rgba(255, 255, 255, 0.98)',
    surfaceVariant: 'rgba(254, 242, 242, 0.95)',
    text: '#450A0A',
    textSecondary: '#7F1D1D',
    chatBubbleUser: '#DC2626',
    chatBubbleBot: '#FEF2F2',
    statusIndicator: '#FBBF24',
    particles: ['#DC2626', '#FBBF24', '#1A2E40', '#EF4444'],
  },
  
  success: {
    name: 'Success',
    background: 'linear-gradient(135deg, #059669 0%, #10B981 50%, #34D399 100%)',
    backgroundAlt: 'linear-gradient(135deg, #ECFDF5 0%, #D1FAE5 100%)',
    primary: '#059669',
    primaryDark: '#047857',
    secondary: '#FF6B35',
    accent: '#FBBF24',
    surface: 'rgba(255, 255, 255, 0.98)',
    surfaceVariant: 'rgba(236, 253, 245, 0.95)',
    text: '#064E3B',
    textSecondary: '#065F46',
    chatBubbleUser: '#059669',
    chatBubbleBot: '#ECFDF5',
    statusIndicator: '#34D399',
    particles: ['#059669', '#34D399', '#FBBF24', '#10B981'],
  },
  
  oci: {
    name: 'OCI Services',
    background: 'linear-gradient(135deg, #0EA5E9 0%, #38BDF8 50%, #7DD3FC 100%)',
    backgroundAlt: 'linear-gradient(135deg, #F0F9FF 0%, #E0F2FE 100%)',
    primary: '#0EA5E9',
    primaryDark: '#0284C7',
    secondary: '#FF6B35',
    accent: '#FBBF24',
    surface: 'rgba(255, 255, 255, 0.98)',
    surfaceVariant: 'rgba(240, 249, 255, 0.95)',
    text: '#0C4A6E',
    textSecondary: '#075985',
    chatBubbleUser: '#0EA5E9',
    chatBubbleBot: '#F0F9FF',
    statusIndicator: '#38BDF8',
    particles: ['#0EA5E9', '#38BDF8', '#FF6B35', '#FBBF24'],
  },
  
  night: {
    name: 'Night Mode',
    background: 'linear-gradient(135deg, #0F172A 0%, #1E293B 50%, #334155 100%)',
    backgroundAlt: 'linear-gradient(135deg, #1E293B 0%, #334155 100%)',
    primary: '#60A5FA',
    primaryDark: '#3B82F6',
    secondary: '#34D399',
    accent: '#FBBF24',
    surface: 'rgba(30, 41, 59, 0.98)',
    surfaceVariant: 'rgba(51, 65, 85, 0.95)',
    text: '#F1F5F9',
    textSecondary: '#94A3B8',
    chatBubbleUser: '#3B82F6',
    chatBubbleBot: '#334155',
    statusIndicator: '#34D399',
    particles: ['#60A5FA', '#34D399', '#FBBF24', '#F472B6'],
  },
};

// Keywords to detect theme context
const THEME_KEYWORDS = {
  passport: ['passport', 'renew', 'renewal', 'new passport', 'lost passport', 'stolen passport', 'tatkal'],
  visa: ['visa', 'tourist visa', 'business visa', 'student visa', 'e-visa', 'visa application', 'visa status'],
  emergency: ['emergency', 'urgent', 'help', 'lost', 'stolen', 'accident', 'hospital', 'police', 'arrest', 'death', 'missing'],
  success: ['thank', 'thanks', 'completed', 'done', 'successful', 'approved', 'received'],
  oci: ['oci', 'overseas citizen', 'oci card', 'pio', 'indian origin'],
};

// Create Theme Context
const ThemeContext = createContext(null);

export const ThemeProvider = ({ children }) => {
  const [currentTheme, setCurrentTheme] = useState('welcome');
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [particlesEnabled, setParticlesEnabled] = useState(true);
  
  // Check for time-based theme
  useEffect(() => {
    const hour = new Date().getHours();
    if (hour >= 20 || hour < 6) {
      // Night mode after 8 PM or before 6 AM
      // setCurrentTheme('night'); // Uncomment to enable auto night mode
    }
  }, []);
  
  // Detect theme from message content
  const detectThemeFromMessage = useCallback((message) => {
    if (!message) return null;
    
    const lowerMessage = message.toLowerCase();
    
    // Check for emergency first (highest priority)
    if (THEME_KEYWORDS.emergency.some(kw => lowerMessage.includes(kw))) {
      return 'emergency';
    }
    
    // Check for success indicators
    if (THEME_KEYWORDS.success.some(kw => lowerMessage.includes(kw))) {
      return 'success';
    }
    
    // Check for service-specific themes
    for (const [theme, keywords] of Object.entries(THEME_KEYWORDS)) {
      if (keywords.some(kw => lowerMessage.includes(kw))) {
        return theme;
      }
    }
    
    return null;
  }, []);
  
  // Change theme with transition
  const changeTheme = useCallback((themeName, animate = true) => {
    if (!THEMES[themeName] || themeName === currentTheme) return;
    
    if (animate) {
      setIsTransitioning(true);
      setTimeout(() => {
        setCurrentTheme(themeName);
        setTimeout(() => setIsTransitioning(false), 300);
      }, 150);
    } else {
      setCurrentTheme(themeName);
    }
  }, [currentTheme]);
  
  // Auto-detect and change theme based on conversation
  const updateThemeFromConversation = useCallback((messages) => {
    if (!messages || messages.length === 0) return;
    
    // Check last 3 messages for context
    const recentMessages = messages.slice(-3);
    for (const msg of recentMessages.reverse()) {
      const detected = detectThemeFromMessage(msg.content);
      if (detected && detected !== currentTheme) {
        changeTheme(detected);
        break;
      }
    }
  }, [currentTheme, detectThemeFromMessage, changeTheme]);
  
  const theme = THEMES[currentTheme];
  
  const value = {
    theme,
    currentTheme,
    changeTheme,
    updateThemeFromConversation,
    detectThemeFromMessage,
    isTransitioning,
    particlesEnabled,
    setParticlesEnabled,
    availableThemes: Object.keys(THEMES),
    THEMES,
  };
  
  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

// Animated Background Component
export const AnimatedBackground = ({ children }) => {
  const { theme, isTransitioning, particlesEnabled } = useTheme();
  
  return (
    <div 
      className="min-h-screen relative overflow-hidden transition-all duration-500"
      style={{ 
        background: theme.background,
        opacity: isTransitioning ? 0.8 : 1,
      }}
    >
      {/* Animated Gradient Orbs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div 
          className="absolute -top-1/2 -left-1/2 w-full h-full rounded-full opacity-30 animate-blob"
          style={{ background: `radial-gradient(circle, ${theme.particles[0]} 0%, transparent 70%)` }}
        />
        <div 
          className="absolute -bottom-1/2 -right-1/2 w-full h-full rounded-full opacity-30 animate-blob animation-delay-2000"
          style={{ background: `radial-gradient(circle, ${theme.particles[1]} 0%, transparent 70%)` }}
        />
        <div 
          className="absolute top-1/4 right-1/4 w-1/2 h-1/2 rounded-full opacity-20 animate-blob animation-delay-4000"
          style={{ background: `radial-gradient(circle, ${theme.particles[2]} 0%, transparent 70%)` }}
        />
      </div>
      
      {/* Floating Particles */}
      {particlesEnabled && (
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          {[...Array(20)].map((_, i) => (
            <div
              key={i}
              className="absolute rounded-full opacity-40 animate-float"
              style={{
                width: `${Math.random() * 8 + 4}px`,
                height: `${Math.random() * 8 + 4}px`,
                background: theme.particles[i % theme.particles.length],
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 5}s`,
                animationDuration: `${Math.random() * 10 + 10}s`,
              }}
            />
          ))}
        </div>
      )}
      
      {/* Glass overlay for better readability */}
      <div 
        className="absolute inset-0 backdrop-blur-[1px]"
        style={{ background: 'rgba(255, 255, 255, 0.05)' }}
      />
      
      {/* Content */}
      <div className="relative z-10">
        {children}
      </div>
    </div>
  );
};

// Theme-aware Card Component
export const ThemeCard = ({ children, variant = 'default', className = '', ...props }) => {
  const { theme } = useTheme();
  
  const variants = {
    default: {
      background: theme.surface,
      border: `1px solid rgba(0,0,0,0.08)`,
    },
    glass: {
      background: theme.surfaceVariant,
      backdropFilter: 'blur(20px)',
      border: '1px solid rgba(255,255,255,0.2)',
    },
    elevated: {
      background: theme.surface,
      boxShadow: '0 8px 32px rgba(0,0,0,0.12)',
    },
  };
  
  return (
    <div
      className={`rounded-2xl transition-all duration-300 ${className}`}
      style={variants[variant]}
      {...props}
    >
      {children}
    </div>
  );
};

export default { ThemeProvider, useTheme, AnimatedBackground, ThemeCard, THEMES };
