import websocket
from utils import pretty_print

class STPWebSocket(websocket.WebSocket):

    def __init__(self, socket, headers, buffer, path, context, stp_connection):
        websocket.WebSocket.__init__(self, socket, headers, buffer, path)
        self.context = context
        self.debug = context.debug
        self.debug_format = context.format
        self.debug_format_payload = context.format_payload
        self._stp_connection = stp_connection
        self._stp_connection.set_msg_handler(self.handle_scope_message)
        
    """
    stp-1 message format
    message type: 1 = command, 2 = response, 3 = event, 4 = error
    message TransportMessage
    {
        required string service = 1;
        required uint32 commandID = 2;
        required uint32 format = 3;
        optional uint32 status = 4;
        optional uint32 tag = 5;
        required binary payload = 8;
    }
    """
    
    # messages sent from scope
    def handle_scope_message(self, msg):
        message = '["%s",%s,%s,%s,%s]' % (
            msg[1], # service
            msg[2], # command
            msg[4], # status
            msg[5], # tag
            msg[8], # payload
        )
        if self.debug:
            pretty_print("send to client:", 
                          msg, 
                          self.debug_format, 
                          self.debug_format_payload)
        self.send_message(message)

    # messages sent from the client    
    def handle_message(self, message):
        # format: "['" SERVICE "'," COMMAND_ID "," STATUS "," TAG "," PAYLOAD "]"
        message = message[1:-1]
        pos = message.find("[")
        args = message[0:pos].split(',')
        self._stp_connection.send_command_STP_1({
                0: 1, # message type
                1: args[0][1:-1], # service
                2: int(args[1]), # command id
                3: 1, # stp message format, JSON
                5: int(args[3]), # tag
                8: message[pos:], # payload
            })
