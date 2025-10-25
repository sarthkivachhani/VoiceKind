// content.js
(() => {
  // Highlight styles
  const HIGHLIGHT_ID = 'voiceclick-hover-highlight';
  function makeHighlight() {
    let el = document.getElementById(HIGHLIGHT_ID);
    if (!el) {
      el = document.createElement('div');
      el.id = HIGHLIGHT_ID;
      el.style.position = 'absolute';
      el.style.zIndex = '2147483647';
      el.style.pointerEvents = 'none';
      el.style.transition = 'all 0.06s ease';
      el.style.border = '2px solid rgba(0,150,255,0.9)';
      el.style.background = 'rgba(0,150,255,0.08)';
      document.body.appendChild(el);
    }
    return el;
  }
  const hl = makeHighlight();

  let lastHighlighted = null;

  function updateHighlight(target) {
    if (!target || target === document.body || target === document.documentElement) {
      hl.style.width = '0px';
      hl.style.height = '0px';
      lastHighlighted = null;
      return;
    }
    const rect = target.getBoundingClientRect();
    hl.style.left = (rect.left + window.scrollX) + 'px';
    hl.style.top = (rect.top + window.scrollY) + 'px';
    hl.style.width = rect.width + 'px';
    hl.style.height = rect.height + 'px';
    lastHighlighted = target;
  }

  // Update highlight on mouse move
  window.addEventListener('mousemove', (e) => {
    const el = document.elementFromPoint(e.clientX, e.clientY);
    updateHighlight(el);
  }, { passive: true });

  // Also update on scroll (cursor stays)
  window.addEventListener('scroll', () => {
    if (lastHighlighted) updateHighlight(lastHighlighted);
  }, { passive: true });

  // WebSocket connection (for commands from Python)
  const ws = new WebSocket("ws://localhost:8765");
  ws.addEventListener('open', () => console.log("content.js: ws open"));
  ws.addEventListener('message', (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (!msg.command) return;
      const command = msg.command.toLowerCase().trim();
      console.log("content.js command:", command);
      // The existing click-by-text logic (unchanged)
      const selectors = ["button", "a", "input[type='submit']", "input[type='button']"];
      const allEls = selectors.flatMap(sel => Array.from(document.querySelectorAll(sel)));
      let el = allEls.find(e => (e.innerText || e.value || "").trim().toLowerCase() === command);
      if (!el) el = allEls.find(e => (e.innerText || e.value || "").toLowerCase().includes(command));
      if (!el) el = Array.from(document.querySelectorAll("[aria-label], [title]")).find(e => ((e.getAttribute("aria-label")||e.title)||"").toLowerCase().includes(command));
      if (el) {
        el.click();
        console.log("content.js: clicked element", el);
      } else {
        console.warn("content.js: no element found for", command);
      }
    } catch (err) {
      console.error("content.js parse error", err, evt.data);
    }
  });
  ws.addEventListener('close', () => console.log("content.js: ws closed"));
  ws.addEventListener('error', (e) => console.error("content.js: ws error", e));
})();
