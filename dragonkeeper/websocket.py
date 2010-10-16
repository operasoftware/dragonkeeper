# spec http://dev.w3.org/html5/websockets/

import asyncore
import hashlib
from struct import pack
from common import CRLF, BUFFERSIZE

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

class WebSocket(asyncore.dispatcher):

    def __init__(self, socket, headers, buffer, path):
        asyncore.dispatcher.__init__(self, sock=socket)
        self._inbuffer = buffer
        self._outbuffer = ''
        self._headers = headers
        self._path = path
        self._handle_read = self._read_request_token
        self._handle_read()

    def _read_request_token(self):
        if len(self._inbuffer) >= 8:
            req_token = self._inbuffer[0:8]
            self._inbuffer = self._inbuffer[9:]
            m = hashlib.md5()
            m.update(self._get_number(self._headers['Sec-WebSocket-Key1']))
            m.update(self._get_number(self._headers['Sec-WebSocket-Key2']))
            m.update(req_token)
            self._outbuffer += RESPONSE_UPGRADE_WEB_SOCKET % (
                self._headers['Origin'],
                "ws://%s/%s" % (self._headers['Host'], self._path),
                m.digest())
            self._handle_read = self._read_message
            self._handle_read()

    def _read_message(self):
        if MSG_END in self._inbuffer:
            start = self._inbuffer.find(MSG_START)
            end = self._inbuffer.find(MSG_END)
            self.handle_message(self._inbuffer[start+1:end])
            self._inbuffer = self._inbuffer[end+1:]
            self._handle_read()

    def handle_message(self, message):
        pass

    def send_message(self, message):
        self._outbuffer += MSG_START + message + MSG_END

    def _get_number(self, in_str):
        n = int(''.join([i for i in in_str if i.isdigit()])) / in_str.count(' ')
        return pack("!I", n)

    # ============================================================
    # Implementations of the asyncore.dispatcher class methods
    # ============================================================

    def handle_read(self):
        self._inbuffer += self.recv(BUFFERSIZE)
        self._handle_read()

    def writable(self):
        return bool(self._outbuffer)

    def handle_write(self):
        sent = self.send(self._outbuffer)
        self._outbuffer = self._outbuffer[sent:]

    def handle_close(self):
        self.close()
