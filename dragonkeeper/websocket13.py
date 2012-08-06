# spec http://tools.ietf.org/html/draft-ietf-hybi-thewebsocketprotocol-17

import asyncore
import hashlib
import base64
from array import array
from common import CRLF, BUFFERSIZE

WS13_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
NOT_SET = -1
INT16 = 2
INT64 = 8
BYTE = 1
OPCODE_CLOSE = 8

# RESPONSE_UPGRADE_WEB_SOCKET % (key)
RESPONSE_UPGRADE_WEB_SOCKET = CRLF.join(["HTTP/1.1 101 Switching Protocols",
                                         "Upgrade: websocket",
                                         "Connection: Upgrade",
                                         "Sec-WebSocket-Accept: %s", CRLF])

class WebSocket13(asyncore.dispatcher):

    # Sec-WebSocket-Version: 13

    def __init__(self, socket, headers, buffer, path):
        asyncore.dispatcher.__init__(self, sock=socket)
        self._inbuffer = array("B", buffer)
        self._outbuffer = ""
        self._headers = headers
        self._path = path
        self._shake_hands()

    def _shake_hands(self):
        sha1 = hashlib.sha1()
        sha1.update(self._headers.get("Sec-WebSocket-Key"))
        sha1.update(WS13_GUID)
        res_key = base64.b64encode(sha1.digest())
        self._outbuffer += RESPONSE_UPGRADE_WEB_SOCKET % res_key
        self._fin = NOT_SET
        self._rsv1 = NOT_SET
        self._rsv2 = NOT_SET
        self._rsv3 = NOT_SET
        self._opcode = NOT_SET
        self._mask = None
        self._data_length = 0
        self._buf_cur = 0
        self._set_read_handler(self._read_fin)

    def _read_fin(self):
        if len(self._inbuffer) >= 2:
            byte = self._inbuffer[self._buf_cur]
            self._buf_cur += 1
            # final frame
            self._fin = byte >> 7
            # reserves
            self._rsv1 = byte >> 6 & 1
            self._rsv2 = byte >> 5 & 1
            self._rsv3 = byte >> 4 & 1
            # opcode
            #
            # 0   continuation frame
            # 1   text frame
            # 2   binary frame
            # 3-7 are reserved for further non-control frames
            # 8   connection close
            self._opcode = byte & 0x0f
            byte = self._inbuffer[self._buf_cur]
            self._buf_cur += 1
            has_mask = byte >> 7
            plen = byte & 0x7f
            if not has_mask or self._opcode == OPCODE_CLOSE:
                self.close()
            else:
                if plen > 125:
                    self._int_size = INT16 if plen == 126 else INT64
                    self._set_read_handler(self._read_int)
                else:
                    self._data_length = plen
                    self._set_read_handler(self._read_mask)

    def _read_int(self):
        if len(self._inbuffer) >= self._buf_cur + self._int_size:
            self._data_length = 0
            for i in range(self._int_size):
                self._data_length <<= 8
                self._data_length += self._inbuffer[self._buf_cur + i]
            self._buf_cur += self._int_size
            self._set_read_handler(self._read_mask)

    def _read_mask(self):
        if len(self._inbuffer) >= self._buf_cur + 4:
            self._mask = self._inbuffer[self._buf_cur:self._buf_cur + 4]
            self._buf_cur += 4
            self._set_read_handler(self._read_payload)

    def _read_payload(self):
        if len(self._inbuffer) >= self._buf_cur + self._data_length:
            buf = self._inbuffer
            cur = self._buf_cur
            mask = self._mask
            r = xrange(self._data_length)
            data = array("B", (buf[cur + i] ^ mask[i % 4] for i in r))
            self.handle_message(data.tostring())
            self._inbuffer = buf[cur + self._data_length:]
            self._buf_cur = 0
            self._fin = NOT_SET
            self._set_read_handler(self._read_fin)

    def _set_read_handler(self, reader):
        self._handle_read = reader
        self._handle_read()

    def _pack(self, *values):
        self._outbuffer += array("B", (value >> (byte_count - 1 - i) * 8 & 0xff
                                       for value, byte_count in values
                                       for i in range(byte_count))).tostring()

    def send_message(self, message):
        # only support for text so far
        msg_len = len(message)
        fin_opcode = 0x81
        if msg_len > 0xffff:
            self._pack((fin_opcode, BYTE), (127, BYTE), (msg_len, INT64))
        elif msg_len > 125:
            self._pack((fin_opcode, BYTE), (126, BYTE), (msg_len, INT16))
        else:
            self._pack((fin_opcode, BYTE), (msg_len, BYTE))
        self._outbuffer += message

    def handle_message(self, message):
        # implement in a subclass
        pass

    # ============================================================
    # Implementations of the asyncore.dispatcher class methods
    # ============================================================

    def handle_read(self):
        m = self.recv(BUFFERSIZE)
        self._inbuffer += array('B', m)
        self._handle_read()

    def writable(self):
        return bool(self._outbuffer)

    def handle_write(self):
        sent = self.send(self._outbuffer)
        self._outbuffer = self._outbuffer[sent:]

    def handle_close(self):
        self.close()

class TestWebSocket13(WebSocket13):

    def __init__(self, socket, headers, buffer, path):
        WebSocket13.__init__(self, socket, headers, buffer, path)

    def handle_message(self, message):
        self.send_message("message received: %s" % message)
        print "\r", message,

class TestWebSocket13HighLoad(WebSocket13):

    def __init__(self, socket, headers, buffer, path):
        WebSocket13.__init__(self, socket, headers, buffer, path)

    def writable(self):
        self.send_message('["ecmascript-debugger",17,0,0,[14,1118563,0,"timeout"]]')
        self.send_message('["ecmascript-debugger",18,0,0,[14,1118563,"completed"]]')
        return bool(self._outbuffer)

    def handle_close(self):
        self.del_channel()
        self.close()
