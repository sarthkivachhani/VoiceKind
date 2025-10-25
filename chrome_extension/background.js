const ws = new WebSocket("ws://localhost:8765");

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if(msg.command){
        chrome.tabs.query({active: true, currentWindow: true}, function(tabs){
            chrome.scripting.executeScript({
                target: {tabId: tabs[0].id},
                func: (command) => {
                    const allEls = [...document.querySelectorAll("button, a, input[type='submit']")];
                    const el = allEls.find(e => e.innerText.toLowerCase() === command.toLowerCase());
                    if(el) el.click();
                },
                args: [msg.command]
            });
        });
    }
};
