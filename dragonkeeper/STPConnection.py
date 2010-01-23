# Copyright (c) 2008, Opera Software ASA
# license see LICENSE.

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


def decode_varuint(buf):
    if len(buf) == 0:
        return None, buf
    shift = 7
    value = ord(buf[0])
    if value & 0x80 != 0x80:
        return value, buf[1:]
    value &= 0x7f
    for i, c in enumerate(buf[1:10]):
        c = ord(c)
        if c & 0x80:
            value |= ((c & 0x7f) << shift)
        else:
            value |= (c << shift)
            return value, buf[i+1+1:]
        shift += 7
    if shift > 63:
        return False, buf
    return None, buf


class ScopeConnection(asyncore.dispatcher):
    """To handle the socket connection to scope."""
    STP1_PB_STP1 = "STP\x01"
    STP1_PB_TYPE_COMMAND = encode_varuint(1)
    STP1_PB_SERVICE = encode_varuint(1 << 3 | 2)
    STP1_PB_COMMID = encode_varuint(2 << 3 | 0)
    STP1_PB_FORMAT = encode_varuint(3 << 3 | 0)
    STP1_PB_STATUS = encode_varuint(4 << 3 | 0)
    STP1_PB_TAG = encode_varuint(5 << 3 | 0)
    STP1_PB_PAYLOAD = encode_varuint(8 << 3 | 2)

    def __init__(self, conn, addr, context):
        asyncore.dispatcher.__init__(self, sock=conn)
        self.addr = addr
        self.debug = context.debug
        self.debug_format = context.format
        self.debug_format_payload = context.format_payload
        self.verbose_debug = context.verbose_debug
        self.force_stp_0 = context.force_stp_0
        # STP 0 meassages
        self.in_buffer = u""
        self.out_buffer = ""
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
        if self.debug:
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
            """
            t = int(1000*time())
            if t - self._last_time > 1000:
                print self._msg_count
                self._msg_count = 0
                self._last_time = t
            else:
                self._msg_count += 1
            """
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

    def send_command_STP_1(self, msg):
        """ to send a message to scope
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
        if self.debug:
            pretty_print("send to host:", msg,
                            self.debug_format, self.debug_format_payload)
        stp_1_msg = "".join([
            self.STP1_PB_TYPE_COMMAND,
            self.STP1_PB_SERVICE, encode_varuint(len(msg[1])), msg[1],
            self.STP1_PB_COMMID, encode_varuint(msg[2]),
            self.STP1_PB_FORMAT, encode_varuint(msg[3]),
            self.STP1_PB_TAG, encode_varuint(msg[5]),
            self.STP1_PB_PAYLOAD, encode_varuint(len(msg[8])), msg[8]])
        self.out_buffer += (
            self.STP1_PB_STP1 +
            encode_varuint(len(stp_1_msg)) +
            stp_1_msg)
        self.handle_write()

    def set_initializer_STP_1(self):
        """change the read handler to the STP/1 read handler"""
        if self.in_buffer or self.out_buffer:
            raise Exception("read or write buffer is not empty "
                                                "in set_initializer_STP_1")
        self.in_buffer = ""
        self.out_buffer = ""
        self.handle_read = self.read_STP_1_initializer
        self.check_input = None
        self.msg_length = 0

    def read_STP_1_initializer(self):
        """read the STP/1 tolken"""
        self.in_buffer += self.recv(BUFFERSIZE)
        if self.in_buffer.startswith("STP/1\n"):
            self.in_buffer = self.in_buffer[6:]
            scope.set_STP_version('stp-1')
            scope.set_service_list(self._service_list)
            self._service_list = None
            self.handle_read = self.handle_read_STP_1
            self.check_input = self.read_stp1_token
            self.handle_stp1_msg = self.handle_stp1_msg_default
            if self.in_buffer:
                self.check_input()

    def set_msg_handler(self, handler):
        self.handle_stp1_msg = handler

    def clear_msg_handler(self):
        self.handle_stp1_msg = self.handle_stp1_msg_default

    def connect_client(self, callback):
        self.connect_client_callback = callback
        self.handle_stp1_msg = self.handle_connect_client
        """
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
        self.send_command_STP_1({
                0: 1,
                1: "scope",
                2: 3,
                3: 1,
                5: 0,
                8: '["json"]'})

    def handle_connect_client(self, msg):
        if self.debug:
            pretty_print("client connected:", msg,
                            self.debug_format, self.debug_format_payload)
        if msg[1] == "scope" and msg[2] == 3 and msg[4] == 0:
            self.handle_stp1_msg = self.handle_stp1_msg_default
            self.connect_client_callback()
            self.connect_client_callback = None
        else:
            print "conection to host failed in scope.handle_connect_callback"

    def read_stp1_token(self):
        """read the STP\x01 message start token"""
        if self.in_buffer.startswith(self.STP1_PB_STP1):
            self.in_buffer = self.in_buffer[4:]
            self.check_input = self.read_varint
            if self.in_buffer:
                self.check_input()

    def read_varint(self):
        """read STP 1 message length as varint"""
        varint, buffer = decode_varuint(self.in_buffer)
        if not varint == None:
            self.varint = varint
            self.in_buffer = buffer
            self.check_input = self.read_binary
            if self.in_buffer:
                self.check_input()

    def read_binary(self):
        """read binary length of STP 1 message"""
        if len(self.in_buffer) >= self.varint:
            stp1_msg = self.in_buffer[0:self.varint]
            self.in_buffer = self.in_buffer[self.varint:]
            self.varint = 0
            self.check_input = self.read_stp1_token
            self.parse_STP_1_msg(stp1_msg)
            if self.in_buffer:
                self.check_input()

    def handle_read_STP_1(self):
        """general read event handler for STP 1"""
        self.in_buffer += self.recv(BUFFERSIZE)
        self.check_input()

    def parse_STP_1_msg(self, STP_1_msg):
        """parse a STP 1 message
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
        msg_type, STP_1_msg = decode_varuint(STP_1_msg)
        if msg_type == None:
            raise Exception("Message type of STP 1 message cannot be parsed")
        else:
            msg = {
                0: msg_type,
                4: 0,
                5: 0,
                8: '',
            }
            while STP_1_msg:
                key, value, STP_1_msg = self.read_STP_1_msg_part(STP_1_msg)
                msg[key] = value
        if self.verbose_debug:
            pretty_print("read from scope socket connection:", msg,
                self.debug_format, self.debug_format_payload)
        self.handle_stp1_msg(msg)

    def handle_stp1_msg_default(self, msg):
        if connections_waiting:
            connections_waiting.pop(0).return_scope_message_STP_1(msg, self)
        else:
            scope_messages.append(msg)

    def read_STP_1_msg_part(self, msg):
        varint, msg = decode_varuint(msg)
        if not varint == None:
            tag, type = varint >> 3, varint & 7
            if type == 2:
                length, msg = decode_varuint(msg)
                value = msg[0:length]
                return tag, value, msg[length:]
            elif type == 0:
                value, msg = decode_varuint(msg)
                return tag, value, msg
            else:
                raise Exception("Not valid type in STP 1 message")
        else:
            raise Exception("Cannot read STP 1 message part")

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
