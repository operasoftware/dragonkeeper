# Copyright (c) 2008, Opera Software ASA
# license see LICENSE.

"""Overview:

The proxy / server is build as an extension of the asyncore.dispatcher class.
There are two instantiation of SimpleServer to listen on the given ports
for new connection, on for HTTP and the other for STP (ScopeTransferProtocol).
They do dispatch a connection to the appropriate classes, HTTPScopeInterface
for HTTP and ScopeConnection for STP. The client is the application which uses
the HTTP interface to connect to scope, the host is the Opera instance
which exposes the scope interface as a STP connection.

There are also two queues, one for HTTP and one for STP to return a scope
message to the client. Getting a new scope message is performed as GET request
with the path /get-message. If the STP queue is not empty then
the first of that queue is returned, otherwise the request is put
in the HTTP waiting-queue. If a new message arrives on the STP sockets it works
the other way around: if the waiting-queue is not empty, the message is
returned to the first waiting connection, otherwise it's put on
the STP message queue.

In contrast to the previous Java version there is only one waiting connection
for scope messages, the messages are dispatched to the target service
on the client side. The target service is added to the response
as custom header 'X-Scope-Message-Service'.

STP/1 messages have a header and a payload. The header is translated
to custom header fields, the payload is the body of the response:

    X-Scope-Message-Service for the service name
    X-Scope-Message-Command for the command id
    X-Scope-Message-Status for the status code
    X-Scope-Message-Tag for the tag

The server is named Dragonkeeper to stay in the started names pace.

The server supports only one host and one client. The main purpose is
developing Opera Dragonfly.

See also http://dragonfly.opera.com/app/scope-interface for more details.
"""

import re
import httpconnection
from time import time
from common import CRLF, RESPONSE_BASIC, RESPONSE_OK_CONTENT
from common import NOT_FOUND, BAD_REQUEST, get_timestamp, Singleton
# from common import pretty_dragonfly_snapshot
from utils import MessageMap, pretty_print_XML, pretty_print

# the two queues
connections_waiting = []
scope_messages = []

SERVICE_LIST = """<services>%s</services>"""
SERVICE_ITEM = """<service name="%s"/>"""
XML_PRELUDE = """<?xml version="1.0"?>%s"""

class Scope(Singleton):
    """Access layer for HTTPScopeInterface instances to the scope connection"""

    version_map = {
        "stp-1": "STP/1",
        "stp-0": "STP/0",
        }

    def __init__(self):
        self.send_command = self.empty_call
        self.services_enabled = {}
        self.version = 'stp-0'
        self._service_list = []
        self._connection = None
        self._http_connection = None

    def empty_call(self, msg):
        pass

    def set_connection(self, connection):
        """ to register the scope connection"""
        self._connection = connection
        self.send_command = connection.send_command_STP_0

    def set_service_list(self, list):
        """to register the service list"""
        self._service_list = list

    def return_service_list(self, http_connection):
        """to get the service list.
        in STP/1 the request of the service list does trigger to (re) connect
        the client. Only after the Connect command was performed successfully
        the service list is returned to the client. any state must be reset"""
        # empty the scope message queue
        while scope_messages:
            scope_messages.pop()
        if self.version == 'stp-0':
            http_connection.return_service_list(self._service_list)
        elif self.version == 'stp-1':
            if self._connection:
                self._http_connection = http_connection
                self._connection.connect_client(self._connect_callback)
            else:
                http_connection.return_service_list(self._service_list)
        else:
            print "Unsupported version in scope.return_service_list(conn)"

    def set_STP_version(self, version):
        """to register the STP version.
        the version gets set as soon as the STP/1 token is received"""
        if version == "stp-1":
            self.version = "stp-1"
            self.send_command = self._connection.send_command_STP_1
        else:
            print "This stp version is not jet supported"

    def get_STP_version(self):
        return self.version_map[self.version]

    def reset(self):
        self._service_list = []
        self.send_command = self.empty_call
        self.services_enabled = {}
        self._connection = None

    def _connect_callback(self):
        if MessageMap.has_map():
            self._http_connection.return_service_list(self._service_list)
            self._http_connection = None
        else:
            MessageMap(self._service_list, self._connection, 
                self._connect_callback, self._http_connection.print_message_map)

scope = Scope()

class HTTPScopeInterface(httpconnection.HTTPConnection):
    """To expose a HTTP interface of the scope interface.
    
    Documentation of the scope interface itself see:

        http://dragonfly.opera.com/app/scope-interface/

    The first part of the path is the command name, other parts are arguments.
    If there is no matching command, the path is served.

    GET methods:
        STP/0
            /services
                to get a list of available services
            /enable/<service name>
                to enable the given service
            /get-message
                to get a pending message or to wait for the next one
                header informations are added as custom header fields like:
                    X-Scope-Message-Service for the service name 
        STP/1
            /services
                to get a list of available services
            /get-message
                to get a pending message or to wait for the next one
                header informations are added as custom header fields like:
                    X-Scope-Message-Service for the service name 
                    X-Scope-Message-Command for the command id
                    X-Scope-Message-Status for the status code
                    X-Scope-Message-Tag for the tag
                the response body is the message in JSON format 
                (except timeout responses which are still sent as xml)

    POST methods:
        STP/0:
            /post-command/<service name>
                request body: message
        STP/1:
            /post-command/<service-name>/<command-id>/<tag>
                request body: message in JSON format

    The STP/1 HTTP interface supports only JSON format for the messages.

    """

    # scope specific responses

    # RESPONSE_SERVICELIST % ( timestamp, content length content )
    # HTTP/1.1 200 OK
    # Date: %s
    # Server: Dragonkeeper/0.8
    # Cache-Control: no-cache
    # Content-Type: application/xml
    # Content-Length: %s
    #
    # %s

    RESPONSE_SERVICELIST = RESPONSE_OK_CONTENT % (
        '%s',
        'Cache-Control: no-cache' + CRLF,
        'application/xml',
        '%s',
        '%s',
    )

    # RESPONSE_OK_OK % ( timestamp )
    # HTTP/1.1 200 OK
    # Date: %s
    # Server: Dragonkeeper/0.8
    # Cache-Control: no-cache
    # Content-Type: application/xml
    # Content-Length: 5
    #
    # <ok/>

    RESPONSE_OK_OK = RESPONSE_OK_CONTENT % (
        '%s',
        'Cache-Control: no-cache' + CRLF,
        'application/xml',
        len("<ok/>"),
        "<ok/>",
    )

    # RESPONSE_TIMEOUT % ( timestamp )
    # HTTP/1.1 200 OK
    # Date: %s
    # Server: Dragonkeeper/0.8
    # Cache-Control: no-cache
    # Content-Type: application/xml
    # Content-Length: 10
    #
    # <timeout/>

    RESPONSE_TIMEOUT = RESPONSE_OK_CONTENT % (
        '%s',
        'Cache-Control: no-cache' + CRLF,
        'application/xml',
        len('<timeout/>'),
        '<timeout/>',
    )

    # SCOPE_MESSAGE_STP_0 % ( timestamp, service, message length, message )
    # HTTP/1.1 200 OK
    # Date: %s
    # Server: Dragonkeeper/0.8
    # Cache-Control: no-cache
    # X-Scope-Message-Service: %s
    # Content-Type: application/xml
    # Content-Length: %s
    #
    # %s

    SCOPE_MESSAGE_STP_0 = RESPONSE_OK_CONTENT % (
        '%s',
        'Cache-Control: no-cache' + CRLF + \
        'X-Scope-Message-Service: %s' + CRLF,
        'application/xml',
        '%s',
        '%s',
    )

    # SCOPE_MESSAGE_STP_1 % ( timestamp, service, command, status,
    #                                           tag, message length, message )
    # HTTP/1.1 200 OK
    # Date: %s
    # Server: Dragonkeeper/0.8
    # Cache-Control: no-cache
    # X-Scope-Message-Service: %s
    # X-Scope-Message-Command: %s
    # X-Scope-Message-Status: %s
    # X-Scope-Message-Tag: %s
    # Content-Type: text/plain
    # Content-Length: %s
    #
    # %s
    SCOPE_MESSAGE_STP_1 = RESPONSE_OK_CONTENT % (
        '%s',
        'Cache-Control: no-cache' + CRLF + \
        'X-Scope-Message-Service: %s' + CRLF + \
        'X-Scope-Message-Command: %s' + CRLF + \
        'X-Scope-Message-Status: %s' + CRLF + \
        'X-Scope-Message-Tag: %s' + CRLF,
        'text/plain',
        '%s',
        '%s',
    )

    def __init__(self, conn, addr, context):
        httpconnection.HTTPConnection.__init__(self, conn, addr, context)
        self.debug = context.debug
        self.debug_format = context.format
        self.debug_format_payload = context.format_payload
        self.print_message_map = context.print_message_map
        # for backward compatibility
        self.scope_message = self.get_message
        self.send_command = self.post_command

    # ============================================================
    # GET commands ( first part of the path )
    # ============================================================
    def services(self):
        """to get the service list"""
        if connections_waiting:
            print ">>> failed, connections_waiting is not empty"
        scope.return_service_list(self)
        self.timeout = 0

    def return_service_list(self, serviceList):
        content = SERVICE_LIST % "".join(
            [SERVICE_ITEM % service.encode('utf-8')
            for service in serviceList])
        self.out_buffer += self.RESPONSE_SERVICELIST % (
            get_timestamp(),
            len(content),
            content)

    def get_stp_version(self):
        content = scope.get_STP_version()
        self.out_buffer += RESPONSE_OK_CONTENT % (
            get_timestamp(),
            '',
            "text/plain",
            len(content),
            content)
        self.timeout = 0

    def enable(self):
        """to enable a scope service"""
        service = self.arguments[0]
        if scope.services_enabled[service]:
            print ">>> service is already enabled", service
        else:
            scope.send_command("*enable %s" % service)
            scope.services_enabled[service] = True

            if service.startswith('stp-'):
                scope.set_STP_version(service)

        self.out_buffer += self.RESPONSE_OK_OK % get_timestamp()
        self.timeout = 0

    def get_message(self):
        """general call to get the next scope message"""
        if scope_messages:
            if scope.version == 'stp-1':
                self.return_scope_message_STP_1(scope_messages.pop(0), self)
            else:
                self.return_scope_message_STP_0(scope_messages.pop(0), self)
            self.timeout = 0
        else:
            connections_waiting.append(self)
        # TODO correct?

    # ============================================================
    # POST commands
    # ============================================================
    def post_command(self):
        """send a command to scope"""
        raw_data = self.raw_post_data
        is_ok = False
        if scope.version == "stp-1":
            args = self.arguments
            """
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
            /send-command/" + service + "/" + command_id + "/" + tag
            """
            scope.send_command({
                    0: 1, # message type
                    1: args[0],
                    2: int(args[1]),
                    3: 1,
                    5: int(args[2]),
                    8: self.raw_post_data,
                })
            is_ok = True
        else:
            service = self.arguments[0]
            if service in scope.services_enabled:
                if not raw_data.startswith("<?xml") and \
                     not raw_data.startswith("STP/1"):
                    raw_data = XML_PRELUDE % raw_data
                msg = "%s %s" % (service, raw_data.decode('UTF-8'))
                scope.send_command(msg)
                is_ok = True
            else:
                print "tried to send a command before %s was enabled" % service
        self.out_buffer += (is_ok and
                            self.RESPONSE_OK_OK or
                            BAD_REQUEST) % get_timestamp()
        self.timeout = 0

    def snapshot(self):
        """store a markup snapshot"""
        raw_data = self.raw_post_data
        if raw_data:
            name, data = raw_data.split(CRLF, 1)
            f = open(name + ".xml", 'wb')
            # f.write(pretty_dragonfly_snapshot(data))
            data = data.replace("'=\"\"", "")
            data = re.sub(r'<script(?:[^/>]|/[^>])*/>[ \r\n]*', '', data)
            f.write(data.replace("'=\"\"", ""))
            f.close()
        self.out_buffer += self.RESPONSE_OK_OK % get_timestamp()
        self.timeout = 0

    # ============================================================
    # STP 0
    # ============================================================
    def return_scope_message_STP_0(self, msg, sender):
        """ return a message to the client"""
        service, payload = msg
        if self.debug:
            pretty_print_XML("\nsend to client: %s" % service, payload, self.debug_format)
        self.out_buffer += self.SCOPE_MESSAGE_STP_0 % (
            get_timestamp(),
            service,
            len(payload),
            payload)
        self.timeout = 0
        if not sender == self:
            self.handle_write()

    # ============================================================
    # STP 1
    # ============================================================
    def return_scope_message_STP_1(self, msg, sender):
        """ return a message to the client
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
        if not msg[8]:
            # workaround, status 204 does not work
            msg[8] = ' '
        if self.debug:
            pretty_print("send to client:", msg,
                                self.debug_format, self.debug_format_payload)
        self.out_buffer += self.SCOPE_MESSAGE_STP_1 % (
            get_timestamp(),
            msg[1], # service
            msg[2], # command
            msg[4], # status
            msg[5], # tag
            len(msg[8]),
            msg[8], # payload
        )
        self.timeout = 0
        if not sender == self:
            self.handle_write()

    def timeouthandler(self):
        if self in connections_waiting:
            connections_waiting.remove(self)
            if not self.command in ["get_message", "scope_message"]:
                print ">>> failed, wrong connection type in queue"
            self.out_buffer += self.RESPONSE_TIMEOUT % get_timestamp()
        else:
            self.out_buffer += NOT_FOUND % (get_timestamp(), 0, '')
        self.timeout = 0
    
    def flush(self):
        if self.timeout:
            self.timeouthandler()
            
        

    # ============================================================
    # Implementations of the asyncore.dispatcher class methods
    # ============================================================
    def writable(self):
        if self.timeout and time() > self.timeout and not self.out_buffer:
            self.timeouthandler()
        return bool(self.out_buffer)

    def handle_close(self):
        if self in connections_waiting:
            connections_waiting.remove(self)
        self.close()
