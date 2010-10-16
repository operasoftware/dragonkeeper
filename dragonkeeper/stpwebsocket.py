import websocket

class STPWebSocket(websocket.WebSocket):

    def __init__(self, httpconnection):
        websocket.WebSocket.__init__(self, httpconnection)

    def handle_message(self, message):
        self.send_message('message received: '+message);

