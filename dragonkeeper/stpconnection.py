import socket
import asyncore
import codecs
from time import time
from random import randint
from common import BLANK, BUFFERSIZE
from httpscopeinterface import connections_waiting, scope_messages, scope
from utils import pretty_print_XML, pretty_print

def encode_varuint(value):
    if value == 0:
        return "\0"
    out = ""
    value = value & 0xffffffffffffffff
    while value:
        part = value & 0x7f
        value >>= 7
        if value:
            part |= 0x80
        out += chr(part)
    return out

"""
msg_type: 1 = command, 2 = response, 3 = event, 4 = error
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
STP1_COMMAND = "".join([encode_varuint(1),
                        encode_varuint(SERVICE << 3 | 2), "%s", "%s",
                        encode_varuint(COMMAND << 3 | 0), "%s",
                        encode_varuint(FORMAT << 3 | 0), "%s",
                        encode_varuint(TAG << 3 | 0), "%s",
                        encode_varuint(PAYLOAD << 3 | 2), "%s", "%s"])
STP1_MSG = "STP\x01%s%s"

class ScopeConnection(asyncore.dispatcher):

    def __init__(self, conn, addr, context):
        asyncore.dispatcher.__init__(self, sock=conn)
        self.addr = addr
        self.debug = context.debug
        self.debug_format = context.format
        self.debug_format_payload = context.format_payload
        self.verbose_debug = context.verbose_debug
        self.debug_only_errors = context.only_errors
        self.force_stp_0 = context.force_stp_0
        # STP 0 meassages
        self.in_buffer = u""
        self.out_buffer = ""
        self.buf_cursor = 0
        self.handle_read = self.handle_read_STP_0
        self.check_input = self.read_int_STP_0
        self.msg_length = 0
        self.stream = codecs.lookup('UTF-16BE').streamreader(self)
        # STP 1 messages
        self.connect_client_callback = None
        self.varint = 0
        self._service_list = None
        scope.set_connection(self)
        self._msg_count = 0
        self._last_time = 0
        self.REQUEST_URI = "stp connection"

    # ============================================================
    # STP 0
    # ============================================================
    # Initialisation, command and message flow for STP 0
    #
    #             Opera              proxy                 client
    #
    # *services     ---------------->
    #                                     ----------------->   *services
    #                                     <-----------------   *enable
    # *enable       <----------------
    # data          <--------------------------------------->  data
    #                                 ....
    #                                     <------------------  *quit
    # *disable      <----------------
    # *quit         ---------------->
    #                                     ------------------>  *hostquit
    #                                     ------------------>  *quit
    #
    # See also http://dragonfly.opera.com/app/scope-interface for more details.

    def send_command_STP_0(self, msg):
        """ to send a message to scope"""
        if self.debug and not self.debug_only_errors:
            service, payload = msg.split(BLANK, 1)
            pretty_print_XML("\nsend to scope: %s" % service, payload, self.debug_format)
        self.out_buffer += ("%s %s" % (len(msg), msg)).encode("UTF-16BE")
        self.handle_write()

    def send_STP0_message_to_client(self, command, msg):
        """send a message to the client"""
        if connections_waiting:
            connections_waiting.pop(0).return_scope_message_STP_0(
                    (command, msg), self)
        else:
            scope_messages.append((command, msg))

    def read_int_STP_0(self):
        """read int STP 0 message"""
        if BLANK in self.in_buffer:
            raw_int, self.in_buffer = self.in_buffer.split(BLANK, 1)
            self.msg_length = int(raw_int)
            self.check_input = self.read_msg_STP_0
            self.check_input()

    def read_msg_STP_0(self):
        """read length STP 0 message"""
        if len(self.in_buffer) >= self.msg_length:
            command, msg = self.in_buffer[0:self.msg_length].split(BLANK, 1)
            self.in_buffer = self.in_buffer[self.msg_length:]
            self.msg_length = 0
            msg = msg.encode("UTF-8")
            command = command.encode("UTF-8")
            if command == "*services":
                services = msg.split(',')
                print "services available:\n ", "\n  ".join(services)
                if not self.force_stp_0 and 'stp-1' in services:
                    self.set_initializer_STP_1()
                    self.send_command_STP_0('*enable stp-1')
                    self._service_list = services
                else:
                    scope.set_service_list(services)
                for service in services:
                    scope.services_enabled[service] = False
            elif command in scope.services_enabled:
                self.send_STP0_message_to_client(command, msg)

            self.check_input = self.read_int_STP_0
            self.check_input()

    def read(self, max_length):
        """to let the codec streamreader class treat
        the class itself like a file object"""
        try:
            return self.recv(max_length)
        except socket.error:
            return ''

    def handle_read_STP_0(self):
        """general read event handler for STP 0"""
        self.in_buffer += self.stream.read(BUFFERSIZE)
        self.check_input()

    # ============================================================
    # STP 1
    # ============================================================
    # Initialisation of STP 1
    # see also scope-transport-protocol.txt and scope-stp1-services.txt
    #
    # If stp-1 is in the service list it will get enabled on receiving
    # the service list in this class ( the stp 1handshake ).
    # The command "services" in the http interface ( HTTPScopeInterface )
    # is treated as (re)load event of the client. That event triggers the
    # Connect command ( which also resets any state for that client
    # in the host ), executed in the Scope class. If the command succeeds
    # the service list is returnd to the client. From this point on the control
    # is up to the client.
    #
    #  ~~~~~~~~~> Handshake
    #  ~ ~ ~ ~ ~> Handshake response
    #  ---------> Command
    #  - - - - -> Response
    #  =========> Event
    #
    # The client must then initiate the handshake which also determines the STP
    # version to use, for instance to enable STP version 1::
    #
    #               Host               client
    #
    #   *services     =================>
    #                 <~~~~~~~~~~~~~~~~~  *enable stp-1
    #   STP/1\n       ~ ~ ~ ~ ~ ~ ~ ~ ~>
    #                 <~~~~~~~~~~~~~~~~~  scope.Connect
    #   scope.Connect ~ ~ ~ ~ ~ ~ ~ ~ ~>
    #
    # Typical message flow between a client, proxy and host looks like this:
    #
    #               Opera               proxy                 client
    #
    #   handshake       <~~~~~~~~~~~~~~~~     ~ ~ ~ ~ ~ ~ ~ ~ ~>  handshake
    #                                         <-----------------  scope.Connect
    #   scope.Connect   <----------------
    #                   - - - - - - - - >
    #                                         - - - - - - - - ->  scope.Connect
    #                                         <-----------------  scope.Enable
    #   scope.Enable    <----------------
    #                   - - - - - - - - >
    #                                         - - - - - - - - ->  scope.Enable
    #
    #   messages        <-------------------  - - - - - - - - ->  messages
    #   events          =======================================>
    #                                     ....
    #                                         <-----------------  scope.Disconnect
    #   scope.Disconnect<----------------
    #                   - - - - - - - - >
    #                                         - - - - - - - - ->  scope.Disconnect
    #
    #
    # See also http://dragonfly.opera.com/app/scope-interface for more details.

    def set_initializer_STP_1(self):
        if self.in_buffer or self.out_buffer:
            raise Exception("read or write buffer is not empty in set_initializer_STP_1")
        self.in_buffer = ""
        self.out_buffer = ""
        self.handle_read = self.read_STP_1_initializer
        self.check_input = None
        self.msg_length = 0

    def read_STP_1_initializer(self):
        self.in_buffer += self.recv(BUFFERSIZE)
        if self.in_buffer.startswith("STP/1\n"):
            self.in_buffer = self.in_buffer[6:]
            scope.set_STP_version("stp-1")
            scope.set_service_list(self._service_list)
            self._service_list = None
            self.buf_cursor = 4
            self.handle_read = self.handle_read_STP_1
            self.handle_stp1_msg = self.handle_stp1_msg_default
            if self.in_buffer: self.handle_read()

    def send_command_STP_1(self, msg):
        if self.debug and not self.debug_only_errors:
            pretty_print("send to host:", msg, self.debug_format, self.debug_format_payload)
        stp_1_cmd = STP1_COMMAND % (encode_varuint(len(msg[SERVICE])), msg[SERVICE],
                                    encode_varuint(msg[COMMAND]),
                                    encode_varuint(msg[FORMAT]),
                                    encode_varuint(msg[TAG]),
                                    encode_varuint(len(msg[PAYLOAD])), msg[PAYLOAD])
        self.out_buffer += STP1_MSG % (encode_varuint(len(stp_1_cmd)), stp_1_cmd)
        self.handle_write()

    def handle_read_STP_1(self):
        self.in_buffer += self.recv(BUFFERSIZE)
        while True:
            if not self.varint:
                varint = self.decode_varuint()
                if varint == None: break
                else: self.varint = varint
            else:
                pos = self.buf_cursor + self.varint
                if len(self.in_buffer) >= pos:
                    self.parse_STP_1_msg(pos)
                    self.varint = 0
                    if len(self.in_buffer) > BUFFERSIZE:
                        self.in_buffer = self.in_buffer[pos:]
                        self.buf_cursor = 4
                    else: self.buf_cursor = pos + 4
                else: break

    def parse_STP_1_msg(self, end_pos):
        msg_type = self.decode_varuint()
        if msg_type == None:
            raise Exception("Message type of STP 1 message cannot be parsed")
        else:
            msg = {TYPE: msg_type, STATUS: 0, TAG: 0, PAYLOAD: ""}
            while self.buf_cursor < end_pos:
                varint = self.decode_varuint()
                if not varint == None:
                    tag, type = varint >> 3, varint & 7
                    if type == 2:
                        length = self.decode_varuint()
                        pos = self.buf_cursor
                        msg[tag] = self.in_buffer[pos:pos + length]
                        self.buf_cursor += length
                    elif type == 0:
                        value = self.decode_varuint()
                        msg[tag] = value
                    else: raise Exception("Not valid type in STP 1 message")
                else: raise Exception("Cannot read STP 1 message part")
        self.handle_stp1_msg(msg)

    def handle_stp1_msg_default(self, msg):
        if connections_waiting:
            connections_waiting.pop(0).return_scope_message_STP_1(msg, self)
        else:
            scope_messages.append(msg)

    def set_msg_handler(self, handler):
        self.handle_stp1_msg = handler

    def clear_msg_handler(self):
        self.handle_stp1_msg = self.handle_stp1_msg_default

    def connect_client(self, callback):
        self.connect_client_callback = callback
        self.handle_stp1_msg = self.handle_connect_client
        self.send_command_STP_1({TYPE: 1,
                                 SERVICE: "scope",
                                 COMMAND: 3,
                                 FORMAT: 1,
                                 TAG: 0,
                                 PAYLOAD: '["json"]'})

    def handle_connect_client(self, msg):
        if self.debug and not self.debug_only_errors:
            pretty_print("client connected:", msg, self.debug_format, self.debug_format_payload)
        if msg[SERVICE] == "scope" and msg[COMMAND] == 3 and msg[STATUS] == 0:
            self.handle_stp1_msg = self.handle_stp1_msg_default
            self.connect_client_callback()
            self.connect_client_callback = None
        else:
            print "conection to host failed in scope.handle_connect_callback"

    def decode_varuint(self):
        value = 0
        buf_len = len(self.in_buffer)
        pos = self.buf_cursor
        for i in [0, 7, 14, 21, 28, 35, 42, 49, 56, 63]:
            if pos >= buf_len: return None
            c = ord(self.in_buffer[pos])
            pos += 1
            if c & 0x80: value += c - 128 << i
            else:
                value += c << i
                self.buf_cursor = pos
                return value
        return None

    # ============================================================
    # Implementations of the asyncore.dispatcher class methods
    # ============================================================

    def handle_read(self):
        pass

    def writable(self):
        return (len(self.out_buffer) > 0)

    def handle_write(self):
        sent = self.send(self.out_buffer)
        self.out_buffer = self.out_buffer[sent:]

    def handle_close(self):
        scope.reset()
        self.close()
