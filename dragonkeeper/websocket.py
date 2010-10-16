# spec http://dev.w3.org/html5/websockets/

import hashlib
from struct import pack
from common import CRLF
import httpconnection

# RESPONSE_UPGRADE_WEB_SOCKET % (REQUEST_ORIGIN,
#                                "ws://%s/%s/ % (domain, path),
#                                response_token)
RESPONSE_UPGRADE_WEB_SOCKET = \
    'HTTP/1.1 101 WebSocket Protocol Handshake' + CRLF + \
    'Upgrade: WebSocket' + CRLF + \
    'Connection: Upgrade' + CRLF + \
    'Sec-WebSocket-Origin: %s' + CRLF + \
    'Sec-WebSocket-Location: %s' + 2 * CRLF + \
    '%s'

MSG_START = "\x00"
MSG_END = "\xff"

class WebSocket(httpconnection.HTTPConnection):

    def __init__(self, http_connection):
        http_connection.del_channel()
        httpconnection.HTTPConnection.__init__(self,
                                               http_connection.socket,
                                               http_connection.addr,
                                               http_connection.context)
        self.in_buffer = http_connection.in_buffer
        self.out_buffer = http_connection.out_buffer
        self.headers = http_connection.headers
        self.path = http_connection.path
        self.check_input = self._read_req_token
        self.check_input()

    def _read_req_token(self):
        if len(self.in_buffer) >= 8:
            req_token = self.in_buffer[0:8]
            self.in_buffer = self.in_buffer[8:]
            m = hashlib.md5()
            m.update(self._get_number(self.headers['Sec-WebSocket-Key1']))
            m.update(self._get_number(self.headers['Sec-WebSocket-Key2']))
            m.update(req_token)
            self.out_buffer += RESPONSE_UPGRADE_WEB_SOCKET % (
                self.headers['Origin'],
                "ws://%s/%s" % (self.headers['Host'], self.path),
                m.digest())
            self.timeout = 0
            self.check_input = self._read_message
            self.check_input()

    def _read_message(self):
        if MSG_END in self.in_buffer:
            start = self.in_buffer.find(MSG_START)
            end = self.in_buffer.find(MSG_END)
            self.handle_message(self.in_buffer[start + 1:end])
            self.in_buffer = self.in_buffer[end + 1:]
            self.check_input()

    def handle_message(self, message):
        pass

    def send_message(self, message):
        self.out_buffer += MSG_START + message + MSG_END

    def _get_number(self, in_str):
        n = int(''.join([i for i in in_str if i.isdigit()])) / in_str.count(' ')
        return pack("!i", n & 0xffffffff)
