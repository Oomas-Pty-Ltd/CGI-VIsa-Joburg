/**
 * ====================================================================
 * SEVA SETU BOT - EMBED SCRIPT
 * ====================================================================
 * 
 * Add this script to your website to embed the Seva Setu Bot chat widget.
 * 
 * INSTALLATION:
 * Add the following code before the </body> tag of your website:
 * 
 * <script src="https://consular-genius.preview.emergentagent.com/embed.js"></script>
 * <script>
 *   SevaSetu.init({
 *     position: 'bottom-right',  // or 'bottom-left'
 *     primaryColor: '#E06F2C',
 *     greeting: 'Namaste! How can I help you?'
 *   });
 * </script>
 * 
 * ====================================================================
 */

(function() {
  'use strict';
  
  // Configuration
  const BOT_URL = 'https://consular-genius.preview.emergentagent.com';
  const API_URL = BOT_URL + '/api/consular/chat-widget';
  
  // Default settings
  const defaults = {
    position: 'bottom-right',
    primaryColor: '#E06F2C',
    greeting: '🙏 Namaste! How can I help you with consular services?',
    headerTitle: 'Seva Setu Assistant',
    headerSubtitle: 'Consulate General of India',
    placeholder: 'Type your question...',
    zIndex: 9999
  };
  
  // State
  let isOpen = false;
  let isMinimized = false;
  let sessionId = null;
  let messages = [];
  let settings = {};
  
  // Generate unique session ID
  function generateSessionId() {
    return 'widget_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
  }
  
  // Create widget HTML
  function createWidget() {
    const container = document.createElement('div');
    container.id = 'seva-setu-widget';
    container.innerHTML = `
      <style>
        #seva-setu-widget * {
          box-sizing: border-box;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        }
        
        .ss-button {
          position: fixed;
          ${settings.position === 'bottom-left' ? 'left: 24px;' : 'right: 24px;'}
          bottom: 24px;
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background: ${settings.primaryColor};
          border: none;
          cursor: pointer;
          box-shadow: 0 4px 20px rgba(0,0,0,0.2);
          display: flex;
          align-items: center;
          justify-content: center;
          transition: transform 0.3s, box-shadow 0.3s;
          z-index: ${settings.zIndex};
        }
        
        .ss-button:hover {
          transform: scale(1.1);
          box-shadow: 0 6px 25px rgba(0,0,0,0.3);
        }
        
        .ss-button svg {
          width: 28px;
          height: 28px;
          fill: white;
        }
        
        .ss-badge {
          position: absolute;
          top: -2px;
          right: -2px;
          width: 14px;
          height: 14px;
          background: #22c55e;
          border-radius: 50%;
          border: 2px solid white;
          animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        
        .ss-chat {
          position: fixed;
          ${settings.position === 'bottom-left' ? 'left: 24px;' : 'right: 24px;'}
          bottom: 24px;
          width: 380px;
          height: 500px;
          background: white;
          border-radius: 16px;
          box-shadow: 0 10px 40px rgba(0,0,0,0.2);
          display: none;
          flex-direction: column;
          overflow: hidden;
          z-index: ${settings.zIndex};
        }
        
        .ss-chat.open {
          display: flex;
        }
        
        .ss-header {
          background: linear-gradient(135deg, ${settings.primaryColor}, ${adjustColor(settings.primaryColor, -20)});
          color: white;
          padding: 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        
        .ss-header-info {
          display: flex;
          align-items: center;
          gap: 12px;
        }
        
        .ss-avatar {
          width: 40px;
          height: 40px;
          background: rgba(255,255,255,0.2);
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 20px;
        }
        
        .ss-header-text h3 {
          margin: 0;
          font-size: 14px;
          font-weight: 600;
        }
        
        .ss-header-text p {
          margin: 2px 0 0;
          font-size: 11px;
          opacity: 0.8;
        }
        
        .ss-header-actions {
          display: flex;
          gap: 8px;
        }
        
        .ss-header-btn {
          background: rgba(255,255,255,0.2);
          border: none;
          border-radius: 6px;
          padding: 6px;
          cursor: pointer;
          color: white;
          transition: background 0.2s;
        }
        
        .ss-header-btn:hover {
          background: rgba(255,255,255,0.3);
        }
        
        .ss-messages {
          flex: 1;
          overflow-y: auto;
          padding: 16px;
          background: #f9fafb;
        }
        
        .ss-message {
          margin-bottom: 12px;
          display: flex;
        }
        
        .ss-message.user {
          justify-content: flex-end;
        }
        
        .ss-message-content {
          max-width: 80%;
          padding: 10px 14px;
          border-radius: 12px;
          font-size: 14px;
          line-height: 1.4;
        }
        
        .ss-message.user .ss-message-content {
          background: ${settings.primaryColor};
          color: white;
          border-bottom-right-radius: 4px;
        }
        
        .ss-message.bot .ss-message-content {
          background: white;
          color: #1f2937;
          border: 1px solid #e5e7eb;
          border-bottom-left-radius: 4px;
        }
        
        .ss-typing {
          display: flex;
          gap: 4px;
          padding: 12px 14px;
        }
        
        .ss-typing span {
          width: 8px;
          height: 8px;
          background: ${settings.primaryColor};
          border-radius: 50%;
          animation: bounce 1.4s infinite ease-in-out;
        }
        
        .ss-typing span:nth-child(2) { animation-delay: 0.2s; }
        .ss-typing span:nth-child(3) { animation-delay: 0.4s; }
        
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-6px); }
        }
        
        .ss-input-area {
          padding: 12px;
          background: white;
          border-top: 1px solid #e5e7eb;
        }
        
        .ss-input-wrap {
          display: flex;
          gap: 8px;
        }
        
        .ss-input {
          flex: 1;
          padding: 10px 14px;
          border: 1px solid #d1d5db;
          border-radius: 8px;
          font-size: 14px;
          outline: none;
          transition: border-color 0.2s;
        }
        
        .ss-input:focus {
          border-color: ${settings.primaryColor};
        }
        
        .ss-send {
          padding: 10px 16px;
          background: ${settings.primaryColor};
          color: white;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          transition: background 0.2s;
        }
        
        .ss-send:hover {
          background: ${adjustColor(settings.primaryColor, -15)};
        }
        
        .ss-send:disabled {
          background: #d1d5db;
          cursor: not-allowed;
        }
        
        .ss-powered {
          text-align: center;
          padding: 8px;
          font-size: 11px;
          color: #9ca3af;
        }
        
        @media (max-width: 480px) {
          .ss-chat {
            width: calc(100% - 32px);
            height: calc(100% - 100px);
            left: 16px;
            right: 16px;
            bottom: 80px;
          }
        }
      </style>
      
      <button class="ss-button" id="ss-toggle">
        <svg viewBox="0 0 24 24"><path d="M12 3c5.5 0 10 3.58 10 8s-4.5 8-10 8c-1.24 0-2.43-.18-3.53-.5C5.55 21 2 21 2 21c2.33-2.33 2.7-3.9 2.75-4.5C3.05 15.07 2 13.13 2 11c0-4.42 4.5-8 10-8z"/></svg>
        <span class="ss-badge"></span>
      </button>
      
      <div class="ss-chat" id="ss-chat">
        <div class="ss-header">
          <div class="ss-header-info">
            <div class="ss-avatar">🙏</div>
            <div class="ss-header-text">
              <h3>${settings.headerTitle}</h3>
              <p>${settings.headerSubtitle}</p>
            </div>
          </div>
          <div class="ss-header-actions">
            <button class="ss-header-btn" id="ss-minimize" title="Minimize">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
            <button class="ss-header-btn" id="ss-close" title="Close">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>
        
        <div class="ss-messages" id="ss-messages"></div>
        
        <div class="ss-input-area">
          <div class="ss-input-wrap">
            <input type="text" class="ss-input" id="ss-input" placeholder="${settings.placeholder}">
            <button class="ss-send" id="ss-send">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
            </button>
          </div>
          <div class="ss-powered">Powered by Seva Setu Bot</div>
        </div>
      </div>
    `;
    
    document.body.appendChild(container);
    
    // Bind events
    document.getElementById('ss-toggle').addEventListener('click', toggleChat);
    document.getElementById('ss-close').addEventListener('click', closeChat);
    document.getElementById('ss-minimize').addEventListener('click', minimizeChat);
    document.getElementById('ss-send').addEventListener('click', sendMessage);
    document.getElementById('ss-input').addEventListener('keypress', function(e) {
      if (e.key === 'Enter') sendMessage();
    });
  }
  
  function adjustColor(color, percent) {
    const num = parseInt(color.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = (num >> 16) + amt;
    const G = (num >> 8 & 0x00FF) + amt;
    const B = (num & 0x0000FF) + amt;
    return '#' + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 + 
      (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 + 
      (B < 255 ? B < 1 ? 0 : B : 255)).toString(16).slice(1);
  }
  
  function toggleChat() {
    const chat = document.getElementById('ss-chat');
    const button = document.getElementById('ss-toggle');
    
    if (isOpen) {
      closeChat();
    } else {
      chat.classList.add('open');
      button.style.display = 'none';
      isOpen = true;
      
      // Show greeting on first open
      if (messages.length === 0) {
        addMessage('bot', settings.greeting);
      }
      
      document.getElementById('ss-input').focus();
    }
  }
  
  function closeChat() {
    const chat = document.getElementById('ss-chat');
    const button = document.getElementById('ss-toggle');
    
    chat.classList.remove('open');
    button.style.display = 'flex';
    isOpen = false;
  }
  
  function minimizeChat() {
    closeChat();
  }
  
  function addMessage(role, content) {
    messages.push({ role, content });
    renderMessages();
  }
  
  function renderMessages() {
    const container = document.getElementById('ss-messages');
    container.innerHTML = messages.map(msg => `
      <div class="ss-message ${msg.role === 'user' ? 'user' : 'bot'}">
        <div class="ss-message-content">${formatMessage(msg.content)}</div>
      </div>
    `).join('');
    container.scrollTop = container.scrollHeight;
  }
  
  function formatMessage(text) {
    // Simple markdown-like formatting
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>')
      .replace(/• /g, '&bull; ');
  }
  
  function showTyping() {
    const container = document.getElementById('ss-messages');
    const typing = document.createElement('div');
    typing.className = 'ss-message bot';
    typing.id = 'ss-typing';
    typing.innerHTML = '<div class="ss-message-content"><div class="ss-typing"><span></span><span></span><span></span></div></div>';
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
  }
  
  function hideTyping() {
    const typing = document.getElementById('ss-typing');
    if (typing) typing.remove();
  }
  
  async function sendMessage() {
    const input = document.getElementById('ss-input');
    const sendBtn = document.getElementById('ss-send');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Add user message
    addMessage('user', message);
    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;
    
    // Show typing
    showTyping();
    
    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          session_id: sessionId,
          mode: 'concise'
        })
      });
      
      const data = await response.json();
      
      if (!sessionId) {
        sessionId = data.session_id;
      }
      
      hideTyping();
      addMessage('bot', data.response);
      
    } catch (error) {
      console.error('Seva Setu Error:', error);
      hideTyping();
      addMessage('bot', 'I apologize, I\'m having trouble connecting. Please try again.');
    } finally {
      input.disabled = false;
      sendBtn.disabled = false;
      input.focus();
    }
  }
  
  // Public API
  window.SevaSetu = {
    init: function(options) {
      settings = Object.assign({}, defaults, options);
      sessionId = generateSessionId();
      
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createWidget);
      } else {
        createWidget();
      }
    },
    
    open: function() {
      if (!isOpen) toggleChat();
    },
    
    close: function() {
      if (isOpen) closeChat();
    },
    
    sendMessage: function(text) {
      document.getElementById('ss-input').value = text;
      sendMessage();
    }
  };
})();
