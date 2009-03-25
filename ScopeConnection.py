import socket
import asyncore
import codecs
from common import *



class ScopeConnection(asyncore.dispatcher):
    """To handle the socket connection to scope."""

    def __init__(self, conn, addr, context):        
        asyncore.dispatcher.__init__(self, sock=conn)
        self.addr = addr
        self.debug = context.debug
        self.debug_format = context.format
        # STP 0 meassages
        self.in_buffer = u""
        self.out_buffer = ""
        self.handle_read = self.handle_read_STP_0
        self.check_input = self.read_int_STP_0
        self.msg_length = 0
        self.stream = codecs.lookup('UTF-16BE').streamreader(self)
        # STP 1 messages
        self.varint = 0
        self.bit_count = 0
        self.binary_buffer = ""
        self.msg_buffer = []
        self.parse_state = 0
        self.parse_msg_state = ""
        scope.setConnection(self)

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

    def send_command_STP_0(self, msg):
        """ to send a message to scope"""
        if self.debug:
            if self.debug_format:
                service, payload = msg.split(BLANK, 1)
                print "\nsend to scope:", service, formatXML(payload)
            else:
                print "send to scope:", msg
        self.out_buffer += ("%s %s" % (len(msg), msg)).encode("UTF-16BE")
        self.handle_write()


        
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
            msg = msg.encode("UTF-8")
            command = command.encode("UTF-8")
            if command == "*services":
                services = msg.split(',')
                print "services available:\n ", "\n  ".join(services)
                scope.setServiceList(services)
                for service in services:
                    scope.commands_waiting[service] = []
                    scope.services_enabled[service] = False
            elif command in scope.services_enabled:
                if connections_waiting:
                    connections_waiting.pop(0).sendScopeEventSTP0(
                            (command, msg), self)
                else:
                    scope_messages.append((command, msg))
            self.in_buffer = self.in_buffer[self.msg_length:]
            self.msg_length = 0
            self.check_input = self.read_int_STP_0
            self.check_input()

    def read(self, max_length):
        """to let the codec stramreader class treat 
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

    def send_command_STP_1(self, msg):
        """ to send a message to scope"""
        service, command, type, tag, data = msg
        if self.debug:
            if self.debug_format:
                print "\nsend to scope:", prettyPrint(
                                (service, command, 0, type, 0, tag, data))
            else:
                print "send to scope:", service, command, type, tag,  data
        self.out_buffer += ( 
            encode_varuint(service) + 
            encode_varuint(command) + 
            encode_varuint(type) +
            "\0" +
            encode_varuint(tag) + 
            encode_varuint(len(data)) + 
            data +
            "\0" 
            )
        self.handle_write()

    def setInitializerSTP_1(self):
        """chnge the read handler to the STP/1 read handler"""
        if self.in_buffer or self.out_buffer:
            raise Exception("read or write buffer is not empty "
                                                "in setInitializerSTP_1")
        self.in_buffer = ""
        self.out_buffer = ""
        self.handle_read = self.read_STP_1_initializer
        self.check_input = None
        self.msg_length = 0

    def read_STP_1_initializer(self):
        """read the STP/1 tolken"""
        self.in_buffer += self.recv(BUFFERSIZE)
        if self.in_buffer.startswith("STP/1\n"):
            print self.in_buffer[0:6]
            self.in_buffer = self.in_buffer[6:]
            self.handle_read = self.handle_read_STP_1
            self.check_input = self.read_varint
            if self.in_buffer:
                self.check_input()
            
    def read_varint(self):
        """read varint STP 1 message"""
        while self.in_buffer:
            byte, self.in_buffer = ord(self.in_buffer[0]), self.in_buffer[1:]
            self.varint += ( byte & 0x7f ) << self.bit_count * 7
            self.bit_count += 1
            CHUNKSIZE = 5
            TYPE_FIELD = 2
            if not byte & 0x80:
                if self.parse_state == CHUNKSIZE:
                    if self.varint:
                        self.check_input = self.read_binary
                    else:
                        self.msg_buffer.append(self.binary_buffer)
                        self.handleMessageSTP1()
                else:
                    if self.parse_state == TYPE_FIELD:
                        self.msg_buffer.extend(
                                    [self.varint >> 2, self.varint & 0x3])
                    else:
                        self.msg_buffer.append(self.varint)
                    self.parse_state += 1
                    self.varint = 0
                    self.bit_count = 0
                break
            if self.bit_count > 8:
                raise Exception("broken varint")
        if self.in_buffer:
            self.check_input()

    def read_binary(self):
        """read length STP 1 message"""
        if len(self.in_buffer) >= self.varint:
            self.binary_buffer += self.in_buffer[0:self.varint]
            self.in_buffer = self.in_buffer[self.varint:]
            self.varint = 0
            self.bit_count = 0
            self.check_input = self.read_varint
            if self.in_buffer:
                self.check_input()

    def handle_read_STP_1(self):
        """general read event handler for STP 1"""
        self.in_buffer += self.recv(BUFFERSIZE)
        self.check_input()

    def handleMessageSTP1(self):
        """process a STP 1 message"""
        # TODO? check service enabled
        if connections_waiting:
            connections_waiting.pop(0).sendScopeEventSTP1(self.msg_buffer, self)
        else:
            scope_messages.append(self.msg_buffer)
        # store hello message
        if self.msg_buffer[0] == 0 and self.msg_buffer[1] == 1:
            scope.storeHelloMessage(self.msg_buffer)
        self.varint = 0
        self.bit_count = 0
        self.binary_buffer = ""
        self.msg_buffer = []
        self.parse_state = 0
        self.parse_msg_state = ""
        
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
