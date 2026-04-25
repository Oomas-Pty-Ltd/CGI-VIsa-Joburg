import React from 'react';
import { createRoot } from 'react-dom/client';
import ChatWidget from './components/ChatWidget';

// Inject Poppins font if not already on the host page
if (!document.querySelector('link[href*="fonts.googleapis.com"][href*="Poppins"]')) {
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = 'https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap';
  document.head.appendChild(link);
}

// Mount the ChatWidget into an isolated container appended to <body>
const container = document.createElement('div');
container.id = 'seva-chatwidget-root';
document.body.appendChild(container);
createRoot(container).render(React.createElement(ChatWidget));
