/**
 * ════════════════════════════════════════════════════════
 * SEVA SETU BOT — EMBEDDABLE WIDGET v2.0
 * Consulate General of India, Johannesburg
 * ════════════════════════════════════════════════════════
 *
 * USAGE — add before </body> on any website:
 *
 *   <script src="https://YOUR_DOMAIN/embed.js"></script>
 *   <script>
 *     SevaSetu.init({
 *       position:     'bottom-right',   // or 'bottom-left'
 *       primaryColor: '#E85D1A',
 *       autoOpen:     false,            // open on page load
 *       openOnClick:  false,            // open on any page click
 *     });
 *   </script>
 *
 * PUBLIC METHODS:
 *   SevaSetu.open()          — open the chat
 *   SevaSetu.close()         — close the chat
 *   SevaSetu.sendMessage(t)  — send a message programmatically
 * ════════════════════════════════════════════════════════
 */

(function () {
  'use strict';

  // ── CONFIG ──────────────────────────────────────────────
  const BOT_URL   = (function(){
    const s = document.currentScript;
    if(s && s.src) return new URL(s.src).origin;
    return window.location.origin;
  })();
  const CHAT_API  = BOT_URL + '/api/consular/chat-widget';

  const AVATAR_SVG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%230B1F3A'/%3E%3Ctext x='50' y='62' text-anchor='middle' font-size='36' fill='%23E85D1A'%3E🙏%3C/text%3E%3C/svg%3E";

  const LANGS = [
    {code:'en', label:'English'},
    {code:'hi', label:'हिंदी'},
    {code:'bn', label:'বাংলা'},
    {code:'mr', label:'मराठी'},
    {code:'te', label:'తెలుగు'},
    {code:'ta', label:'தமிழ்'},
  ];

  const QUICK_ACTIONS = [
    {icon:'🛂', label:'Passport Renewal', query:'Passport renewal process'},
    {icon:'🌍', label:'Visa Services',    query:'Visa services information'},
    {icon:'🪪', label:'OCI Card',         query:'OCI card application'},
    {icon:'📄', label:'Attestation',      query:'Document attestation services'},
    {icon:'📅', label:'Appointment',      query:'Appointment booking'},
    {icon:'📞', label:'Emergency',        query:'Emergency consular contact'},
  ];

  // ── STATE ────────────────────────────────────────────────
  let isOpen      = false;
  let isLoading   = false;
  let sessionId   = 'widget_' + Math.random().toString(36).substr(2,9) + '_' + Date.now();
  let currentLang = 'en';
  let welcomed    = false;
  let settings    = {};
  let typingEl    = null;

  const defaults = {
    position:     'bottom-right',
    primaryColor: '#E85D1A',
    accentColor:  '#1A57D4',
    autoOpen:     false,
    openOnClick:  false,
    zIndex:       9999,
  };

  // ── CSS ──────────────────────────────────────────────────
  function injectStyles() {
    const c = settings.primaryColor;
    const a = settings.accentColor;
    const pos = settings.position === 'bottom-left' ? 'left:28px' : 'right:28px';
    const z = settings.zIndex;

    const css = `
#ss-widget-root*{box-sizing:border-box;margin:0;padding:0;font-family:'Segoe UI',system-ui,-apple-system,sans-serif}
/* FAB */
#ss-fab{position:fixed;${pos};bottom:28px;z-index:${z};width:64px;height:64px;border-radius:50%;background:#fff;border:3px solid ${c};cursor:pointer;box-shadow:0 6px 24px rgba(0,0,0,.18);transition:all .25s cubic-bezier(.34,1.56,.64,1);overflow:hidden;display:flex;align-items:center;justify-content:center}
#ss-fab:hover{transform:scale(1.1)}
#ss-fab img{width:100%;height:100%;object-fit:cover;border-radius:50%}
.ss-badge{position:absolute;top:-1px;right:-1px;width:16px;height:16px;border-radius:50%;background:#16A34A;border:2px solid #fff}
.ss-badge::after{content:'';position:absolute;inset:3px;border-radius:50%;background:rgba(255,255,255,.7);animation:ss-ping 1.6s ease-out infinite}
@keyframes ss-ping{0%{transform:scale(1);opacity:.8}100%{transform:scale(2.5);opacity:0}}
/* POPUP */
#ss-popup{position:fixed;${pos};bottom:104px;z-index:${z - 1};width:390px;background:#fff;border-radius:20px;box-shadow:0 20px 60px rgba(11,31,58,.22),0 4px 16px rgba(0,0,0,.1);display:flex;flex-direction:column;overflow:hidden;transform:scale(0.85) translateY(20px);transform-origin:bottom right;opacity:0;pointer-events:none;transition:all .3s cubic-bezier(.34,1.2,.64,1);max-height:90vh}
#ss-popup.ss-open{transform:scale(1) translateY(0);opacity:1;pointer-events:all}
/* HEADER */
.ss-header{background:linear-gradient(135deg,#0B1F3A,#1A3A6B);padding:0;position:relative;overflow:hidden}
.ss-header::before{content:'';position:absolute;right:-30px;top:-30px;width:130px;height:130px;border-radius:50%;background:rgba(232,93,26,.12)}
.ss-header::after{content:'';position:absolute;left:-20px;bottom:-20px;width:100px;height:100px;border-radius:50%;background:rgba(26,87,212,.12)}
.ss-htop{display:flex;align-items:center;justify-content:space-between;padding:14px 16px 10px;position:relative;z-index:1}
.ss-hav{display:flex;align-items:center;gap:12px}
.ss-av{width:46px;height:46px;border-radius:50%;border:2.5px solid ${c};overflow:hidden;flex-shrink:0;box-shadow:0 0 0 3px rgba(232,93,26,.2)}
.ss-av img{width:100%;height:100%;object-fit:cover}
.ss-hname{font-size:14px;font-weight:700;color:#fff;line-height:1.2}
.ss-hsub{font-size:10.5px;color:rgba(255,255,255,.6);margin-top:2px}
.ss-hstatus{display:flex;align-items:center;gap:5px;margin-top:4px}
.ss-sdot{width:7px;height:7px;border-radius:50%;background:#4ADE80;animation:ss-pulse 1.4s ease infinite}
@keyframes ss-pulse{0%,100%{opacity:1}50%{opacity:.5}}
.ss-stext{font-size:10px;color:#4ADE80;font-weight:500}
.ss-hbtns{display:flex;gap:6px;position:relative;z-index:1}
.ss-hbtn{width:30px;height:30px;border-radius:7px;border:none;background:rgba(255,255,255,.12);color:rgba(255,255,255,.8);cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:14px;transition:background .2s}
.ss-hbtn:hover{background:rgba(255,255,255,.22);color:#fff}
/* LANG BAR */
.ss-langs{background:rgba(0,0,0,.22);padding:7px 14px;display:flex;align-items:center;gap:6px;overflow-x:auto;scrollbar-width:none;position:relative;z-index:1}
.ss-langs::-webkit-scrollbar{display:none}
.ss-lang-lbl{font-size:9.5px;color:rgba(255,255,255,.4);white-space:nowrap;margin-right:2px;font-weight:500;letter-spacing:.04em}
.ss-ltag{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.16);color:rgba(255,255,255,.78);font-size:9.5px;font-weight:500;padding:3px 8px;border-radius:9px;white-space:nowrap;cursor:pointer;transition:all .2s;flex-shrink:0}
.ss-ltag:hover,.ss-ltag.ss-active{background:rgba(232,93,26,.7);border-color:${c};color:#fff}
.ss-lmore{background:rgba(26,87,212,.45);border:1px solid rgba(26,87,212,.35);color:#C2D9FF;font-size:9.5px;font-weight:600;padding:3px 8px;border-radius:9px;white-space:nowrap;flex-shrink:0;cursor:default}
/* ADVISORY */
.ss-advisory{background:#FFF9EC;border-bottom:1px solid #FDE68A;padding:7px 13px;display:flex;align-items:flex-start;gap:7px}
.ss-advisory-ico{font-size:13px;flex-shrink:0;margin-top:1px}
.ss-advisory-txt{font-size:10.5px;color:#92400E;line-height:1.5}
.ss-advisory-txt strong{font-weight:600}
/* MESSAGES */
.ss-msgs{flex:1;overflow-y:auto;padding:14px 12px;display:flex;flex-direction:column;gap:10px;background:#F8F9FB;min-height:180px;max-height:320px;scrollbar-width:thin;scrollbar-color:rgba(11,31,58,.12) transparent}
.ss-msgs::-webkit-scrollbar{width:4px}
.ss-msgs::-webkit-scrollbar-thumb{background:rgba(11,31,58,.14);border-radius:2px}
.ss-bot{display:flex;gap:8px;align-items:flex-end}
.ss-bot-av{width:28px;height:28px;border-radius:50%;flex-shrink:0;border:1.5px solid ${c};overflow:hidden}
.ss-bot-av img{width:100%;height:100%;object-fit:cover}
.ss-bbub{background:#fff;border:1px solid #E5E7EB;border-radius:14px 14px 14px 4px;padding:9px 12px;max-width:calc(100% - 44px);box-shadow:0 1px 4px rgba(0,0,0,.05);font-size:12.5px;color:#374151;line-height:1.6}
.ss-bbub p{margin:0 0 4px 0}
.ss-bbub p:last-child{margin-bottom:0}
.ss-bbub .ss-mhi{font-size:12px;font-weight:700;color:#0B1F3A;margin-bottom:4px}
.ss-bbub .ss-mhin{font-size:11px;color:#6B7280;margin-bottom:5px}
.ss-user{display:flex;justify-content:flex-end}
.ss-ubub{background:linear-gradient(135deg,${a},#2768F5);color:#fff;border-radius:14px 14px 4px 14px;padding:9px 12px;max-width:75%;font-size:12.5px;line-height:1.6}
.ss-time{font-size:9.5px;color:#9CA3AF;margin-top:4px;text-align:right}
.ss-utime{font-size:9.5px;color:rgba(255,255,255,.6);margin-top:4px;text-align:right}
/* TYPING */
.ss-typing-dots{display:flex;gap:4px;align-items:center;padding:2px 0}
.ss-typing-dots span{width:6px;height:6px;border-radius:50%;background:#9CA3AF;animation:ss-blink 1.2s ease infinite}
.ss-typing-dots span:nth-child(2){animation-delay:.2s}
.ss-typing-dots span:nth-child(3){animation-delay:.4s}
@keyframes ss-blink{0%,60%,100%{transform:translateY(0);opacity:.4}30%{transform:translateY(-4px);opacity:1}}
/* QUICK ACTIONS */
.ss-qa{padding:8px 12px 0;display:flex;gap:6px;flex-wrap:wrap}
.ss-qbtn{background:#EFF6FF;border:1px solid #BFDBFE;color:#1D4ED8;font-size:10.5px;font-weight:500;padding:5px 10px;border-radius:18px;cursor:pointer;transition:all .2s;white-space:nowrap;font-family:inherit}
.ss-qbtn:hover{background:#DBEAFE;border-color:#93C5FD}
/* INPUT */
.ss-input-area{background:#fff;border-top:1px solid #E5E7EB;padding:10px 14px;display:flex;flex-direction:column;gap:8px}
.ss-textarea{width:100%;resize:none;border:1.5px solid #E5E7EB;border-radius:10px;padding:9px 12px;font-family:inherit;font-size:12.5px;color:#374151;outline:none;line-height:1.5;transition:border-color .2s,box-shadow .2s;min-height:64px;max-height:130px;background:#F9FAFB}
.ss-textarea:focus{border-color:${a};background:#fff;box-shadow:0 0 0 3px rgba(26,87,212,.08)}
.ss-textarea::placeholder{color:#B0B8C4;font-size:12px}
.ss-irow{display:flex;align-items:center;justify-content:space-between;gap:6px}
.ss-ilibtn{width:36px;height:36px;border-radius:9px;border:none;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:15px;transition:all .2s}
.ss-ilibtn-mic{background:#FFF0E8;color:${c};border:1.5px solid #FDD0B8}
.ss-ilibtn-mic:hover{background:${c};color:#fff}
.ss-ilibtn-doc{background:#FFF0E8;color:${c};border:1.5px solid #FDD0B8}
.ss-ilibtn-doc:hover{background:${c};color:#fff}
.ss-send{height:36px;padding:0 16px;border-radius:9px;border:none;background:linear-gradient(135deg,${a},#2768F5);color:#fff;font-family:inherit;font-size:12.5px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:5px;transition:all .2s;white-space:nowrap;box-shadow:0 2px 8px rgba(26,87,212,.25)}
.ss-send:hover{filter:brightness(1.08);transform:translateY(-1px)}
.ss-send:disabled{background:#9CA3AF;transform:none;box-shadow:none;cursor:not-allowed}
.ss-footer{text-align:center;padding:5px;font-size:9.5px;color:#9CA3AF;border-top:1px solid #F3F4F6}
.ss-footer span{color:${c};font-weight:500}
/* MOBILE */
@media(max-width:480px){
  #ss-popup{width:calc(100vw - 16px);right:8px!important;left:8px!important;bottom:88px}
}
    `;
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);
  }

  // ── BUILD HTML ───────────────────────────────────────────
  function buildWidget() {
    const root = document.createElement('div');
    root.id = 'ss-widget-root';

    const posStyle = settings.position === 'bottom-left' ? 'left:28px' : 'right:28px';

    // FAB
    const fab = document.createElement('div');
    fab.id = 'ss-fab';
    fab.setAttribute('role','button');
    fab.setAttribute('aria-label','Open Seva Setu chatbot');
    fab.setAttribute('title','Chat with Seva Setu');
    fab.innerHTML = `<img id="ss-fab-img" src="${AVATAR_SVG}" alt="Seva Setu"><span class="ss-badge"></span>`;
    fab.onclick = toggleChat;

    // LANG TAGS HTML
    const langTagsHtml = LANGS.map((l,i) =>
      `<span class="ss-ltag${i===0?' ss-active':''}" data-lang="${l.code}">${l.label}</span>`
    ).join('') + `<span class="ss-lmore">+35 More</span>`;

    // QUICK ACTIONS HTML
    const qaHtml = QUICK_ACTIONS.map(qa =>
      `<button class="ss-qbtn" data-query="${qa.query}">${qa.icon} ${qa.label}</button>`
    ).join('');

    // POPUP
    const popup = document.createElement('div');
    popup.id = 'ss-popup';
    popup.setAttribute('role','dialog');
    popup.setAttribute('aria-label','Seva Setu Chatbot');
    popup.innerHTML = `
      <div class="ss-header">
        <div class="ss-htop">
          <div class="ss-hav">
            <div class="ss-av"><img id="ss-popup-av" src="${AVATAR_SVG}" alt="Seva Setu"></div>
            <div>
              <div class="ss-hname">Seva Setu <span style="font-size:9px;opacity:.6;font-weight:400">सेवा सेतु</span></div>
              <div class="ss-hsub">Consulate General of India, Johannesburg</div>
              <div class="ss-hstatus"><span class="ss-sdot"></span><span class="ss-stext" id="ss-status">Ready to Assist</span></div>
            </div>
          </div>
          <div class="ss-hbtns">
            <button class="ss-hbtn" id="ss-min-btn" title="Minimize">−</button>
            <button class="ss-hbtn" id="ss-close-btn" title="Close">✕</button>
          </div>
        </div>
        <div class="ss-langs">
          <span class="ss-lang-lbl">LANG:</span>
          ${langTagsHtml}
        </div>
      </div>
      <div class="ss-advisory">
        <span class="ss-advisory-ico">⚠️</span>
        <span class="ss-advisory-txt"><strong>Advisory:</strong> For urgent matters, call the consular helpline. Verify documents before visiting.</span>
      </div>
      <div class="ss-msgs" id="ss-msgs"></div>
      <div class="ss-qa" id="ss-qa">${qaHtml}</div>
      <div class="ss-input-area">
        <textarea class="ss-textarea" id="ss-input" rows="2" placeholder="Type your question in English or हिंदी..."></textarea>
        <div class="ss-irow">
          <div style="display:flex;gap:6px">
            <button class="ss-ilibtn ss-ilibtn-mic" id="ss-mic" title="Voice input">🎤</button>
            <button class="ss-ilibtn ss-ilibtn-doc" id="ss-doc" title="Upload document">📎</button>
          </div>
          <button class="ss-send" id="ss-send">➤ Send</button>
        </div>
      </div>
      <div class="ss-footer">Official service of <span>Consulate General of India</span> · Johannesburg</div>
    `;

    root.appendChild(fab);
    root.appendChild(popup);
    document.body.appendChild(root);

    // BIND EVENTS
    popup.querySelector('#ss-min-btn').onclick  = toggleChat;
    popup.querySelector('#ss-close-btn').onclick = closeChat;
    popup.querySelector('#ss-send').onclick      = sendMessage;
    popup.querySelector('#ss-mic').onclick       = doVoice;
    popup.querySelector('#ss-doc').onclick       = doDocUpload;

    const ta = popup.querySelector('#ss-input');
    ta.addEventListener('keydown', e => { if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage();} });
    ta.addEventListener('input', () => { ta.style.height='auto'; ta.style.height=Math.min(ta.scrollHeight,130)+'px'; });

    popup.querySelectorAll('.ss-ltag').forEach(btn =>
      btn.addEventListener('click', () => {
        popup.querySelectorAll('.ss-ltag').forEach(b=>b.classList.remove('ss-active'));
        btn.classList.add('ss-active');
        currentLang = btn.dataset.lang;
        updatePlaceholder(ta);
      })
    );

    popup.querySelectorAll('.ss-qbtn').forEach(btn =>
      btn.addEventListener('click', () => {
        ta.value = btn.dataset.query;
        sendMessage();
      })
    );

    // openOnClick: any click on page opens the widget
    if(settings.openOnClick){
      document.addEventListener('click', e => {
        const p = popup, f = fab;
        if(!p.contains(e.target) && !f.contains(e.target) && !isOpen) toggleChat();
      });
    }

    // Attempt to load bot avatar
    fetch(BOT_URL + '/api/consular/bot-info').then(r=>r.json()).then(d=>{
      if(d.avatar_url){
        document.getElementById('ss-fab-img').src      = d.avatar_url;
        document.getElementById('ss-popup-av').src     = d.avatar_url;
      }
    }).catch(()=>{});

    // Connectivity
    window.addEventListener('online',  updateStatus);
    window.addEventListener('offline', updateStatus);
  }

  // ── OPEN / CLOSE ─────────────────────────────────────────
  function toggleChat() {
    isOpen = !isOpen;
    const popup = document.getElementById('ss-popup');
    popup.classList.toggle('ss-open', isOpen);
    if (isOpen && !welcomed) {
      welcomed = true;
      showWelcome();
      setTimeout(() => { const i = document.getElementById('ss-input'); if(i) i.focus(); }, 350);
    }
  }

  function closeChat() {
    isOpen = false;
    const popup = document.getElementById('ss-popup');
    if(popup) popup.classList.remove('ss-open');
  }

  // ── WELCOME ──────────────────────────────────────────────
  function showWelcome() {
    appendBot(`
      <div class="ss-mhin">🙏 नमस्ते! मैं <strong>सेवा सेतु</strong> हूँ — आपकी सेवा में।</div>
      <div class="ss-mhi">Namaste! 🇮🇳</div>
      <p>I'm <strong>Seva Setu</strong>, your official AI assistant for consular services. I can help with:</p>
      <p>• Passport &amp; Travel Documents<br>• Visa Services (Tourist / Business / Student)<br>• OCI / PIO Cards<br>• Document Attestation<br>• Appointments &amp; Emergency Help</p>
      <p style="margin-top:6px">How can I assist you today?</p>
    `);
  }

  // ── SEND ─────────────────────────────────────────────────
  async function sendMessage() {
    if(isLoading) return;
    const ta  = document.getElementById('ss-input');
    const txt = ta.value.trim();
    if(!txt) return;

    appendUser(txt);
    ta.value = '';
    ta.style.height = 'auto';

    const qa = document.getElementById('ss-qa');
    if(qa) qa.style.display = 'none';

    setLoading(true);
    showTyping();

    try {
      const res = await fetch(CHAT_API, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ message:txt, session_id:sessionId, language:currentLang, mode:'concise' })
      });
      if(!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      if(data.session_id) sessionId = data.session_id;
      removeTyping();
      appendBot(formatText(data.response || data.reply || 'I could not process that request. Please try again.'));
    } catch(err) {
      removeTyping();
      appendBot(navigator.onLine
        ? 'I\'m having trouble reaching the server. Please try again.'
        : 'You appear to be offline. Please check your connection.'
      );
    } finally {
      setLoading(false);
    }
  }

  // ── DOM HELPERS ──────────────────────────────────────────
  function appendUser(text) {
    const msgs = document.getElementById('ss-msgs');
    const d = document.createElement('div');
    d.className = 'ss-user';
    d.innerHTML = `<div class="ss-ubub">${esc(text)}<div class="ss-utime">${now()}</div></div>`;
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function appendBot(html) {
    const msgs = document.getElementById('ss-msgs');
    const av   = (document.getElementById('ss-popup-av') || {}).src || AVATAR_SVG;
    const d = document.createElement('div');
    d.className = 'ss-bot';
    d.innerHTML = `
      <div class="ss-bot-av"><img src="${av}" alt=""></div>
      <div class="ss-bbub">${html}<div class="ss-time">${now()}</div></div>`;
    msgs.appendChild(d);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function showTyping() {
    typingEl = document.createElement('div');
    typingEl.className = 'ss-bot';
    typingEl.id = '__ss-typing__';
    const av = (document.getElementById('ss-popup-av') || {}).src || AVATAR_SVG;
    typingEl.innerHTML = `
      <div class="ss-bot-av"><img src="${av}" alt=""></div>
      <div class="ss-bbub"><div class="ss-typing-dots"><span></span><span></span><span></span></div></div>`;
    const msgs = document.getElementById('ss-msgs');
    msgs.appendChild(typingEl);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function removeTyping() {
    if(typingEl){ typingEl.remove(); typingEl=null; }
  }

  function setLoading(v) {
    isLoading = v;
    const btn = document.getElementById('ss-send');
    if(!btn) return;
    btn.disabled = v;
    btn.textContent = v ? '⏳ Sending…' : '➤ Send';
  }

  function updateStatus() {
    const el = document.getElementById('ss-status');
    if(el) el.textContent = navigator.onLine ? 'Ready to Assist' : 'Offline';
  }

  function updatePlaceholder(ta) {
    const map = {
      en:'Type your question in English or हिंदी...',
      hi:'अपना प्रश्न हिंदी या English में लिखें...',
      bn:'আপনার প্রশ্ন লিখুন...',
      mr:'तुमचा प्रश्न टाइप करा...',
      te:'మీ ప్రశ్నను టైప్ చేయండి...',
      ta:'உங்கள் கேள்வியை தட்டச்சு செய்யுங்கள்...'
    };
    ta.placeholder = map[currentLang] || map.en;
  }

  function now()  { return new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}); }
  function esc(t) { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function formatText(t) {
    return '<p>' + t
      .replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>')
      .replace(/\*(.*?)\*/g,'<em>$1</em>')
      .replace(/\n\n+/g,'</p><p>')
      .replace(/\n/g,'<br>')
      + '</p>';
  }

  // ── VOICE ────────────────────────────────────────────────
  function doVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if(!SR){ alert('Voice input not supported in this browser (try Chrome).'); return; }
    const rec = new SR();
    rec.lang = currentLang === 'hi' ? 'hi-IN' : 'en-IN';
    rec.onresult = e => {
      const ta = document.getElementById('ss-input');
      ta.value = e.results[0][0].transcript;
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight,130)+'px';
    };
    rec.start();
  }

  function doDocUpload() {
    const inp = document.createElement('input');
    inp.type='file';
    inp.accept='.pdf,.jpg,.jpeg,.png,.doc,.docx';
    inp.onchange = () => {
      if(inp.files[0]){
        const ta = document.getElementById('ss-input');
        ta.value = `[Document: ${inp.files[0].name}] Please help me with this document.`;
      }
    };
    inp.click();
  }

  // ── PUBLIC API ───────────────────────────────────────────
  window.SevaSetu = {
    init(options) {
      settings = Object.assign({}, defaults, options);
      const run = () => { injectStyles(); buildWidget(); if(settings.autoOpen) toggleChat(); };
      document.readyState === 'loading'
        ? document.addEventListener('DOMContentLoaded', run)
        : run();
    },
    open()          { if(!isOpen) toggleChat(); },
    close()         { closeChat(); },
    sendMessage(t)  { const ta=document.getElementById('ss-input'); if(ta){ta.value=t; sendMessage();} }
  };

})();
