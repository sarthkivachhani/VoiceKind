const WebSocket = require('ws');
const wss = new WebSocket.Server({ port: 8765 });

wss.on('connection', ws => {
    console.log('Python controller connected');

    ws.on('message', message => {
        console.log('Received:', message);
        // Broadcast to all clients (Chrome extensions)
        wss.clients.forEach(client => {
            if(client.readyState === WebSocket.OPEN){
                client.send(message);
            }
        });
    });

    ws.on('close', () => console.log('Python disconnected'));
});

console.log('WebSocket server running on ws://localhost:8765');
