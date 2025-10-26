// content.js
// Hybrid extension content script
// - Standalone voice + hover highlight
// - Hybrid with Python via ws://localhost:8765
// - Voice: "click login", "open cart", "scroll down", "scroll up"
// - Gesture/WS: receives {x,y} and {"command":...}
// - Finds & clicks best matching clickable element (by visible text, aria-label, title, alt, value, placeholder)
/*
let ws = null;
let lastHoverElement = null;
let lastHoverPoint = { x: null, y: null };

// Utility: determine if element is considered clickable
function isClickable(el) {
  if (!el) return false;
  const tag = el.tagName && el.tagName.toLowerCase();
  const role = el.getAttribute && el.getAttribute("role");
  if (tag === "a" && el.hasAttribute("href")) return true;
  if (tag === "button") return true;
  if (tag === "input" && ["button","submit","image"].includes(el.type)) return true;
  if (el.onclick) return true;
  if (role && ["button","link"].includes(role)) return true;
  if (el.tabIndex >= 0) return true;
  return false;
}

// Utility: get candidate text from element to match voice target
function getElementText(el) {
  if (!el) return "";
  const pieces = [];
  if (el.innerText) pieces.push(el.innerText.trim());
  if (el.getAttribute) {
    const aria = el.getAttribute("aria-label");
    if (aria) pieces.push(aria.trim());
    const alt = el.getAttribute("alt");
    if (alt) pieces.push(alt.trim());
    const title = el.getAttribute("title");
    if (title) pieces.push(title.trim());
    const value = el.value;
    if (value) pieces.push(String(value).trim());
    const ph = el.getAttribute("placeholder");
    if (ph) pieces.push(ph.trim());
  }
  return pieces.join(" ").replace(/\s+/g, " ").toLowerCase();
}

// Find visible clickable elements
function getAllClickables() {
  const selectors = [
    "a[href]",
    "button",
    "input[type='button']",
    "input[type='submit']",
    "[role='button']",
    "[role='link']",
    "[onclick]",
    "[tabindex]"
  ];
  const nodes = Array.from(document.querySelectorAll(selectors.join(",")));
  // filter visible
  return nodes.filter(el => {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    // check visibility computed style
    const style = window.getComputedStyle(el);
    if (style.visibility === "hidden" || style.display === "none" || parseFloat(style.opacity || "1") === 0) return false;
    return true;
  });
}

// Compute simple score for target match: includes + length closeness
function scoreMatch(elText, target) {
  if (!target) return 0;
  const t = target.toLowerCase().trim();
  if (!t) return 0;
  const text = elText || "";
  if (text === t) return 100;
  if (text.includes(t)) return 75 + Math.min(25, t.length); // contains target
  // partial word match
  const words = t.split(/\s+/);
  let count = 0;
  for (const w of words) if (text.includes(w)) count++;
  return Math.min(60, 20 * count);
}

// Choose best clickable by text and proximity (if coords available)
function findBestClickable(target, preferPoint) {
  const candidates = getAllClickables();
  if (candidates.length === 0) return null;
  target = (target || "").toLowerCase().trim();

  let best = null;
  let bestScore = -1;

  for (const el of candidates) {
    const elText = getElementText(el);
    let score = scoreMatch(elText, target);
    // boost for exact role/href if target equals "cart" and element id/class matches
    const idcls = ((el.id || "") + " " + (el.className || "")).toLowerCase();
    if (target && idcls.includes(target)) score += 10;

    // proximity bonus if preferPoint provided
    if (preferPoint && preferPoint.x !== null) {
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width/2 + window.scrollX;
      const cy = rect.top + rect.height/2 + window.scrollY;
      const dx = Math.abs(preferPoint.x - cx);
      const dy = Math.abs(preferPoint.y - cy);
      const dist = Math.hypot(dx, dy);
      // convert dist to bonus: closer gets + up to 20
      const bonus = Math.max(0, 20 - Math.min(20, dist / 30));
      score += bonus;
    }

    if (score > bestScore) {
      bestScore = score;
      best = el;
    }
  }

  // If we found a decent match (>30), return; otherwise fallback to element under cursor if any
  if (best && bestScore >= 30) return best;
  // fallback: if preferPoint given, elementFromPoint or elementsFromPoint
  if (preferPoint && preferPoint.x !== null && preferPoint.y !== null) {
    const clientX = preferPoint.x - window.scrollX;
    const clientY = preferPoint.y - window.scrollY;
    try {
      const els = document.elementsFromPoint(clientX, clientY);
      for (const el of els) {
        if (isClickable(el)) return el;
      }
    } catch (e) {
      // ignore
    }
  }
  // final fallback: first clickable
  return candidates[0] || null;
}

// Highlighting
function highlightElement(el) {
  if (!el) return;
  if (lastHoverElement && lastHoverElement !== el) {
    lastHoverElement.style.outline = "";
  }
  el.style.outline = "3px solid #ff6600";
  lastHoverElement = el;
}

// Clicking with visual flash
function clickElement(el) {
  if (!el) return false;
  highlightElement(el);
  // animate a quick flash
  const prevOutline = el.style.outline;
  el.click();
  // small visual pulse (outline already set)
  setTimeout(() => {
    try { el.style.outline = prevOutline; } catch(e) {}
  }, 450);
  console.log("Clicked element:", el);
  return true;
}

// Click nearest clickable at coords (used when voice fails to match)
function clickNearestAtPoint(x, y) {
  if (x == null || y == null) return false;
  const clientX = x - window.scrollX;
  const clientY = y - window.scrollY;
  try {
    const els = document.elementsFromPoint(clientX, clientY);
    for (const el of els) {
      if (isClickable(el)) {
        clickElement(el);
        return true;
      }
    }
  } catch (e) {
    // elementsFromPoint may throw in some frames; fallback to elementFromPoint
    const el = document.elementFromPoint(clientX, clientY);
    if (isClickable(el)) { clickElement(el); return true; }
  }
  return false;
}

// Handle incoming "command" objects (from WS or internal voice)
function handleCommandObj(obj) {
  if (!obj || !obj.command) return;
  const cmd = String(obj.command).toLowerCase();
  console.log("[extension] command:", cmd, obj);

  // Scroll faster for voice commands sent explicitly as "voice" origin (we assume Python voice sends same)
  if (cmd.includes("scroll up")) {
    // large voice scroll
    window.scrollBy({ top: -800, left: 0, behavior: "smooth" });
    return;
  }
  if (cmd.includes("scroll down")) {
    window.scrollBy({ top: 800, left: 0, behavior: "smooth" });
    return;
  }

  // voice click with explicit target
  // msg can be { command: "click", target: "login" }
  if (cmd === "click" && obj.target) {
    const el = findBestClickable(obj.target, lastHoverPoint);
    if (el) { clickElement(el); return; }
    // fallback: click nearest
    if (clickNearestAtPoint(lastHoverPoint.x, lastHoverPoint.y)) return;
    return;
  }

  // plain click command -> click highlighted element
  if (cmd === "click") {
    if (lastHoverElement) { clickElement(lastHoverElement); return; }
    if (clickNearestAtPoint(lastHoverPoint.x, lastHoverPoint.y)) return;
    return;
  }

  // click by raw text (e.g., "click login")
  let m = cmd.match(/click (.+)/);
  if (m) {
    const target = m[1].trim();
    const el = findBestClickable(target, lastHoverPoint);
    if (el) { clickElement(el); return; }
    if (clickNearestAtPoint(lastHoverPoint.x, lastHoverPoint.y)) return;
    return;
  }

  // open / navigate (basic)
  m = cmd.match(/open (.+)/);
  if (m) {
    let site = m[1].trim();
    if (!/^https?:\/\//.test(site)) site = "https://www." + site;
    window.open(site, "_blank");
    return;
  }

  // fallback: do nothing but log
  console.log("[extension] unhandled command:", cmd);
}

// WebSocket handling (connect to Python if available)
function initWebSocket() {
  try {
    ws = new WebSocket("ws://localhost:8765");
  } catch (e) {
    console.warn("[WS] cannot create websocket", e);
    return;
  }
  ws.onopen = () => console.log("[WS] connected to Python");
  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data);
      // hover coords
      if (data.x !== undefined && data.y !== undefined) {
        lastHoverPoint.x = data.x;
        lastHoverPoint.y = data.y;
        // highlight element at that screen position
        const clientX = data.x - window.scrollX;
        const clientY = data.y - window.scrollY;
        const el = document.elementFromPoint(clientX, clientY);
        if (el) highlightElement(el);
      }
      // command
      if (data.command) {
        handleCommandObj(data);
      }
    } catch (err) {
      console.error("[WS] parse error", err, ev.data);
    }
  };
  ws.onclose = () => {
    console.log("[WS] closed — retry in 2s");
    setTimeout(initWebSocket, 2000);
  };
  ws.onerror = (e) => {
    console.error("[WS] error", e);
    ws.close();
  };
}
initWebSocket();

// ---------------- Voice recognition (standalone) ----------------
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const recog = new SR();
  recog.continuous = true;
  recog.interimResults = false;
  recog.lang = "en-US";

  recog.onresult = (evt) => {
    const r = evt.results[evt.results.length - 1][0].transcript.trim().toLowerCase();
    console.log("[voice]", r);

    // scroll + synonyms handled here (fast voice scroll)
    if (["scroll up","go up","move up","page up"].some(w => r.includes(w))) {
      window.scrollBy({ top: -800, left: 0, behavior: "smooth" });
      return;
    }
    if (["scroll down","go down","move down","page down","go to bottom"].some(w => r.includes(w))) {
      window.scrollBy({ top: 800, left: 0, behavior: "smooth" });
      return;
    }

    // click commands
    let m = r.match(/\b(click|press|tap|open|select)\b\s*(?:the\s)?(.+)?/);
    if (m) {
      const verb = m[1];
      const rest = (m[2] || "").trim();
      if (!rest || rest === "here" || rest === "this" || rest === "that") {
        // click current hover
        if (lastHoverElement) { clickElement(lastHoverElement); return; }
        clickNearestAtPoint(lastHoverPoint.x, lastHoverPoint.y);
        return;
      } else {
        // click by text
        const el = findBestClickable(rest, lastHoverPoint);
        if (el) { clickElement(el); return; }
        // fallback: click nearest
        if (clickNearestAtPoint(lastHoverPoint.x, lastHoverPoint.y)) return;
        return;
      }
    }

    // fallback: send to ws (if connected) as generic command
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ command: r }));
    }
  };

  recog.onerror = (e) => console.error("[voice] error", e);
  recog.onend = () => {
    // auto-restart
    try { recog.start(); } catch (e) {}
  };

  try { recog.start(); console.log("[voice] recognition started"); } catch (e) { console.warn("[voice] start failed", e); }
} else {
  console.warn("No SpeechRecognition API available in this browser.");
}

// ---------------- Mouse hover highlighting (desktop mouse) ----------------
document.addEventListener("mousemove", (e) => {
  lastHoverPoint.x = e.pageX;
  lastHoverPoint.y = e.pageY;
  const el = document.elementFromPoint(e.clientX, e.clientY);
  if (el) highlightElement(el);
});
*/



console.log("Voice + Gesture Accessibility Extension Loaded");

// --- VOICE RECOGNITION SETUP ---
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recog = null;
if (SpeechRecognition) {
  recog = new SpeechRecognition();
  recog.continuous = true;
  recog.interimResults = false;
  recog.lang = "en-US";
  recog.start();
  console.log("Voice recognition started...");
} else {
  console.error("SpeechRecognition not supported in this browser.");
}

// --- HELPER: SITE SEARCH ---
function performSiteSearch(query) {
  if (!query) return false;
  query = query.trim();

  const selectors = [
    "input[type='search']",
    "input[name*='search']",
    "input[id*='search']",
    "input[class*='search']",
    "input[placeholder*='Search']",
    "input[placeholder*='search']",
    "input[type='text']",
    "form[role='search'] input",
    "input[name*='q']"
  ];

  let input = null;
  for (const sel of selectors) {
    const nodeList = Array.from(document.querySelectorAll(sel));
    for (const el of nodeList) {
      try {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        const visible = rect.width > 0 && rect.height > 0 &&
          style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
        if (visible && !el.disabled) { input = el; break; }
      } catch (e) {}
    }
    if (input) break;
  }

  if (input) {
    input.focus();
    input.value = query;

    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));

    const form = input.form || input.closest('form') || input.closest("[role='search']");
    if (form) {
      const submitBtn = form.querySelector("button[type='submit'], input[type='submit'], button");
      if (submitBtn) {
        submitBtn.click();
        return true;
      }
      try {
        form.requestSubmit ? form.requestSubmit() : form.submit();
        return true;
      } catch (e) {}
    }

    const enterEvent = new KeyboardEvent('keydown', { bubbles: true, cancelable: true, key: 'Enter', code: 'Enter' });
    input.dispatchEvent(enterEvent);
    return true;
  }

  const googleUrl = "https://www.google.com/search?q=" + encodeURIComponent(query);
  window.open(googleUrl, "_blank");
  return true;
}

// --- SMOOTH SCROLL FUNCTION ---
function smoothScrollBy(amount) {
  window.scrollBy({ top: amount, behavior: "smooth" });
}

// --- CLICK BUTTON / LINK BY NAME ---
function clickButtonByText(targetText) {
  targetText = targetText.toLowerCase();
  const clickables = Array.from(document.querySelectorAll("a, button, input[type='button'], input[type='submit']"));

  for (const el of clickables) {
    const txt = (el.innerText || el.value || "").toLowerCase().trim();
    if (txt.includes(targetText)) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.click();
      console.log("Clicked:", txt);
      return true;
    }
  }
  console.log("No element found for:", targetText);
  return false;
}

// --- VOICE COMMAND HANDLER ---
if (recog) {
  recog.onresult = (event) => {
    const r = event.results[event.results.length - 1][0].transcript.trim().toLowerCase();
    console.log("[Voice Command]:", r);

    // 1️⃣ SEARCH COMMAND
    const searchMatch = r.match(/\b(?:search|find)(?: for)?\s+(.+)/i);
    if (searchMatch) {
      const query = searchMatch[1].trim();
      performSiteSearch(query);
      return;
    }

    // 2️⃣ SCROLL COMMANDS
    if (/\b(scroll|go)\s*(down|lower|bottom)\b/.test(r)) {
      smoothScrollBy(window.innerHeight * 0.8);
      return;
    }
    if (/\b(scroll|go)\s*(up|higher|top)\b/.test(r)) {
      smoothScrollBy(-window.innerHeight * 0.8);
      return;
    }

    // 3️⃣ CLICK COMMANDS
    if (r.includes("click") || r.includes("open")) {
      let target = r.replace(/(click|open|go to)/g, "").trim();
      if (!target) return;
      clickButtonByText(target);
      return;
    }

    // 4️⃣ PAGE NAVIGATION SHORTCUTS
    if (r.includes("cart")) {
      clickButtonByText("cart");
      return;
    }
    if (r.includes("login") || r.includes("sign in")) {
      clickButtonByText("login");
      return;
    }
    if (r.includes("sign up") || r.includes("register")) {
      clickButtonByText("sign up");
      return;
    }
  };

  recog.onerror = (err) => console.error("Voice recognition error:", err);
  recog.onend = () => recog.start(); // auto restart
}

