🧠 VoiceKind — Voice & Gesture Controlled Interaction System

**VoiceKind** is an intelligent accessibility system that enables seamless **hands-free control** of your computer and browser using **AI-powered voice and gesture recognition**.  
Designed for inclusivity, it empowers users to navigate, scroll, click, and search — all through natural movements and voice commands.

---

🌟 Key Features
 Voice Commands
Control your system and browser using natural voice commands:
- “Scroll down” / “Scroll up”
- “Click on login”
- “Open cart”
- “Search for headphones”
- “Go back”, “Reload page”, etc.

✅ Works across desktop and web.  
✅ Uses **SpeechRecognition (Google API)** or offline mode via **Vosk**.

✋ Gesture Controls
Interact visually using your hand gestures:
- **Move cursor** — Track your index finger position in real-time  
- **Click** — Close your fist to trigger a mouse click  
- **Scroll** — Vertical hand movement to scroll smoothly  
- **Exit mode** — Specific gesture to stop tracking  

✅ Built using **OpenCV** and **Mediapipe** for high accuracy.  
✅ Gesture and voice can work **simultaneously**.  

💻 Hybrid System Architecture
VoiceKind runs as a combination of:
| Component | Role | Tech Used |
|------------|------|-----------|
| 🧩 Python Backend | Handles voice + gesture recognition | OpenCV, Mediapipe, SpeechRecognition |
| 🌐 Chrome Extension | Interacts with web pages | JavaScript, Manifest V3 |
| 🔗 WebSocket Server | Enables real-time data transfer | Python WebSocket library |

⚙️ Tech Stack
- **Python:** OpenCV, Mediapipe, SpeechRecognition, PyAutoGUI  
- **JavaScript (Chrome Extension):** Manifest V3, DOM interaction  
- **WebSocket:** Real-time bridge between Python and Browser  
