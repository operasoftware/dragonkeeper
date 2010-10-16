import websocket

class STPWebSocket(websocket.WebSocket):

    def __init__(self, socket, headers, buffer, path, context):
        websocket.WebSocket.__init__(self, socket, headers, buffer, path)
        self.context = context

    def handle_message(self, message):
        self.send_message('message received: '+message);

