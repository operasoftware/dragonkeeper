import websocket13
from utils import pretty_print
from common import ProfileContext

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

TYPE = 0
SERVICE = 1
COMMAND = 2
FORMAT = 3
STATUS = 4
TAG = 5
PAYLOAD = 8

class STPWebSocket(websocket13.WebSocket13):

    def __init__(self, socket, headers, buffer, path, context, stp_connection):
        websocket13.WebSocket13.__init__(self, socket, headers, buffer, path)
        self.context = context
        self.debug = context.debug
        self.debug_format = context.format
        self.debug_format_payload = context.format_payload
        self._stp_connection = stp_connection
        self._stp_connection.set_msg_handler(self.handle_scope_message)
        self.REQUEST_URI = "web-socket: " + path
        self.profile = ProfileContext("messages per second:")

    # messages sent from scope
    def handle_scope_message(self, msg):
        self.profile.count()
        message = '["%s",%s,%s,%s,%s]' % (msg[SERVICE],
                                          msg[COMMAND],
                                          msg[STATUS],
                                          msg[TAG],
                                          msg[PAYLOAD])
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
        self._stp_connection.send_command_STP_1({TYPE: 1,
                                                 SERVICE: args[0][1:-1],
                                                 COMMAND: int(args[1]),
                                                 FORMAT: 1,
                                                 TAG: int(args[3]),
                                                 PAYLOAD: message[pos:]})
