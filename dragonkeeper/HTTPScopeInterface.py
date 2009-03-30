"""Overview:

The proxy / server is build as an extension of the asyncore.dispatcher class.
There are two instantiation of SimpleServer to listen on the given ports 
for new connection, on for http and the other for scope. They do dispatch a 
connection to the appropriate classes, Connection for http and 
ScopeConnection for scope. 
There are also two queues, one for getting a new scope message and one for 
scope messages. Getting a new scope message is performed as GET request 
with the path /scope-message. If the scope-message queue is not empty then
the first of that queue is returned, otherwise the request is put 
in the waiting-queue. If a new message arrives on the scope sockets it works 
the other way around: if the waiting-queue is not empty, the message is
returned to the first waiting connection, otherwise it's put on 
the scope-message queue.
In contrast to the previous Java version there is only one waiting connection
for scope messages, the messages are dispatched to the correct service 
on the client side. The target service is added to the response 
as custom header 'X-Scope-Message-Service'. This pattern will be extended 
for the STP 1 version.
The server is named Dragonkeeper to stay in the started namespace.
"""


import re
import HTTPConnection
from time import time
from common import CRLF, RESPONSE_BASIC, RESPONSE_OK_CONTENT, getTimestamp



# the two queues
connections_waiting = []
scope_messages = []

commandMap = {
    "scope": {
        0: "OnServices",
        1: "OnConnect",
        2: "OnQuit",
        3: "OnConnectionLost",
        5: "Enable",
        6: "Disable",
        7: "Configure",
        8: "Info",
        9: "Quit"
        },
    "window-manager": {
        1: "GetActiveWindow", 
        3: "ListWindows",
        5: "ModifyFilter",
        0: "OnWindowUpdated",
        2: "OnWindowClosed",
        4: "OnWindowActivated"
        },
    "console-logger": {
        0: "ConsoleMessage"
        },
    "ecmascript-debugger": {
        1: "ListRuntimes",
        2: "ContinueThread",
        3: "Eval",
        4: "ExamineObjects",
        5: "SpotlightObjects",
        6: "AddBreakpoint",
        7: "RemoveBreakpoint",
        8: "AddEventHandler",
        9: "RemoveEventHandler",
        10: "SetConfiguration",
        11: "GetBacktrace",
        12: "Break",
        13: "InspectDom",
        14: "OnRuntimeStarted",
        15: "OnRuntimeStopped",
        16: "OnNewScript",
        17: "OnThreadStarted",
        18: "OnThreadFinished",
        19: "OnThreadStoppedAt",
        20: "OnHandleEvent",
        21: "OnObjectSelected",
        22: "CssGetIndexMap",
        23: "CssGetAllStylesheets",
        24: "CssGetStylesheet",
        25: "CssGetStyleDeclarations",
        26: "GetSelectedObject"
        },
    "http-logger": {
        0: "OnRequest",
        2: "OnResponse"
        }
    }

statusMap = {
    0: "OK",
    1: "Conflict",
    2: "Unsupported Type",
    3: "Bad Request",
    4: "Internal Error",
    5: "Command Not Found",
    6: "Service Not Found",
    7: "Out Of Memory",
    8: "Service Not Enabled",
    9: "Service Already Enabled",
    }

typeMap = {
    0: "protocol-buffer",
    1: "json",
    2: "xml",
    3: "scope"
    }
    
SERVICE_LIST = """<services>%s</services>"""
SERVICE_ITEM = """<service name="%s"/>"""
XML_PRELUDE = """<?xml version="1.0"?>%s"""


class Scope(object):
    """Used as a namespace for scope with methods to register 
    the send command and the service list"""
    def __init__(self):
        self.serviceList = []
        self.sendCommand = self.empty_call
        self.commands_waiting = {}
        self.services_enabled = {}
        self.connection = None
        self.version = 'stp-0'

    def empty_call(self, msg):
        pass
    
    def setConnection(self, connection):
        self.connection = connection
        self.sendCommand = connection.send_command_STP_0

    def setServiceList(self, list):
        self.serviceList = list

    def setSTPVersion(self, version):
        self.version = version
        if version == "stp-1":
            self.connection.setInitializerSTP_1()
            self.sendCommand = self.connection.send_command_STP_1
        else:
            print "This stp version is not jet supported"

    def storeHelloMessage(self, msg):
        self.hello_msg = msg
        """
        services: scope=1.0.0,0,1;console-logger=1.0.0,0,1;...;
        """
        self.serviceMap = {}
        self.serviceIndexMap = {}
        data = msg[6]
        services_raw = data[data.rfind('services:') + len('services:'):]
        for index, service_raw in enumerate(services_raw.strip().split(';')):
            if service_raw:
                service, values = service_raw.split('=')                
                version, active, max_active = values.split(',')
                self.serviceIndexMap[index] = self.serviceMap[service] = {
                    'name': service,
                    'version': version,
                    'active': active,
                    'max-active': max_active,
                    'index': index
                    }
        # print self.serviceIndexMap

            

    def pushbackHelloMessage(self):
        if scope_messages:
            print "len scope_messages:", len(scope_messages)
        scope_messages.append(self.hello_msg)
    def reset(self):
        self.serviceList = []
        self.sendCommand = self.empty_call  
        self.commands_waiting = {}
        self.services_enabled = {}
 
scope = Scope()

def formatXML(in_string):
    """To pretty print STP 0 messages"""
    in_string = re.sub(r"<\?[^>]*>", "", in_string)
    ret = []
    indent_count = 0
    INDENT = "  "
    LF = "\n"
    TEXT = 0
    TAG = 1
    CLOSING_TAG = 2
    OPENING_CLOSING_TAG = 3
    OPENING_TAG = 4
    matches_iter = re.finditer(r"([^<]*)(<(\/)?[^>/]*(\/)?>)", in_string)
    try:
        while True:
            m = matches_iter.next()
            matches = m.groups()
            if matches[CLOSING_TAG]:
                indent_count -= 1
                if matches[TEXT] or last_match == OPENING_TAG:
                    ret.append(m.group())
                else:
                    ret.extend([LF, indent_count * INDENT, m.group()])
                last_match = CLOSING_TAG
            elif matches[OPENING_CLOSING_TAG] or "<![CDATA[" in matches[1]:
                last_match = OPENING_CLOSING_TAG
                ret.extend([LF, indent_count * INDENT, m.group()])
            else:
                last_match = OPENING_TAG
                ret.extend([LF, indent_count * INDENT, m.group()])
                indent_count += 1
    except Exception, msg:
        ret = [in_string]
    return "".join(ret)

def prettyPrint(stp_1_msg):
    # TODO? pretty print data
    # print stp_1_msg
    service, command, status, type, cid, tag, data = stp_1_msg 
    if hasattr(scope, 'serviceIndexMap'):
        service_name = scope.serviceIndexMap[service]['name']
        return ( 
            "  service: %s\n" 
            "  command: %s\n"
            "  status: %s\n"
            "  type: %s\n"
            "  cid: %s\n"
            "  tag: %s\n"
            "  data: %s" 
            ) % (
            service_name, 
            commandMap[service_name][command], 
            statusMap[status], 
            typeMap[type], 
            cid, 
            tag, 
            data
            )
    return stp_1_msg

class HTTPScopeInterface(HTTPConnection.HTTPConnection):
    """To provide a http interface to the scope protocol. 
    The purpose of this interface is mainly to develop Dragonfly, 
    not to used it for actual debugging.

    The first part of the path is the command name, other parts are arguments.
    If there is no matching command, the path is served.
    
    GET methods:
        /services to get a list of available services
        /enable/<service name> to enable the given service
        /scope-message to get a pending message or to wait for the next one
            the target service is added in 
            a custom header field 'X-Scope-Message-Service' 
        /quite to quit the session, not implemented
        
    POST methods:
        send-command/<service name>[/argument]*, message is the post body.
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

    RESPONSE_SERVICELIST =  RESPONSE_OK_CONTENT % ( 
        '%s', 
        'Cache-Control: no-cache' + CRLF, 
        'application/xml', 
        '%s', 
        '%s'
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
        "<ok/>"
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
        '<timeout/>'
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
        '%s'
    )

    SCOPE_MESSAGE_STP_1 = RESPONSE_OK_CONTENT % (
        '%s',
        'Cache-Control: no-cache' + CRLF + \
        'X-Scope-Message-Service: %s' + CRLF + \
        'X-Scope-Message-Command: %s' + CRLF + \
        'X-Scope-Message-Status: %s' + CRLF + \
        'X-Scope-Message-Tag: %s' + CRLF,
        'text/plain',
        '%s',
        '%s'
    )

    """
    SCOPE_MESSAGE_STP_1_EMPTY = RESPONSE_BASIC % (
        204,
        'No Content',
        '%s',
        'Cache-Control: no-cache' + CRLF + \
        'X-Scope-Message-Service: %s' + CRLF + \
        'X-Scope-Message-Command: %s' + CRLF + \
        'X-Scope-Message-Status: %s' + CRLF + \
        'X-Scope-Message-Tag: %s' + 2 * CRLF
    )
    """

    def __init__(self, conn, addr, context):        
        HTTPConnection.HTTPConnection.__init__(self, conn, addr, context)

    # ============================================================
    # GET commands ( first part of the path )
    # ============================================================

    def services(self):
        """to get the service list"""
        if connections_waiting:
            print ">>> failed, connections_waiting is not empty"
        content = SERVICE_LIST % "".join (
            [SERVICE_ITEM % service.encode('utf-8') 
            for service in scope.serviceList] 
            )
        self.out_buffer += self.RESPONSE_SERVICELIST % ( 
            getTimestamp(), 
            len(content), 
            content
            )
        self.timeout = 0

    def enable(self):
        """to enable a scope service"""
        service = self.arguments[0]
        # print 'enable service: ', service
        if scope.services_enabled[service]:
            if path.startswith('stp-'):
                scope.pushbackHelloMessage()
            print ">>> service is already enabled", service
        else:
            scope.sendCommand("*enable %s" % service)
            scope.services_enabled[service] = True
            if service.startswith('stp-'):
                scope.setSTPVersion(service)
            while scope.commands_waiting[service]:
                scope.sendCommand(scope.commands_waiting[service].pop(0))
        self.out_buffer += self.RESPONSE_OK_OK % getTimestamp()
        self.timeout = 0

    def scope_message(self):
        """general call to get the next scope message"""
        if scope_messages:
            if scope.version == 'stp-1':
                self.sendScopeEventSTP1(scope_messages.pop(0), self)
            else:
                self.sendScopeEventSTP0(scope_messages.pop(0), self)
            self.timeout = 0
        else:
            connections_waiting.append(self)
        # TODO correct?
        

    # ============================================================
    # POST commands 
    # ============================================================

    def send_command(self):
        """send a command to scope"""
        raw_data = self.raw_post_data
        if scope.version == "stp-1":
            args = map(int, self.arguments)
            args.append(raw_data)
            scope.sendCommand(args)
        else:
            if not raw_data.startswith("<?xml"):
                raw_data = XML_PRELUDE % raw_data  
            msg = "%s %s" % (self.command, raw_data.decode('UTF-8'))
            if scope.services_enabled[self.command]:
                scope.sendCommand(msg)
            else:
                scope.commands_waiting[self.command].append(msg)
        self.out_buffer += self.RESPONSE_OK_OK % getTimestamp()
        self.timeout = 0
            
    # ============================================================
    # STP 0
    # ============================================================

    def sendScopeEventSTP0(self, msg, sender):
        """ return a message to the client"""
        service, payload = msg
        if self.debug:
            if self.debug_format:
                print "\nsend to client:", service, formatXML(payload)
            else:
                print "send to client:", service, payload
        self.out_buffer += self.SCOPE_MESSAGE_STP_0 % (
            getTimestamp(), 
            service, 
            len(payload), 
            payload
        )
        self.timeout = 0
        if not sender == self:
            self.handle_write()

    # ============================================================
    # STP 1
    # ============================================================

    def sendScopeEventSTP1(self, msg, sender):
        """ return a message to the client"""
        service, command, status, type, cid, tag, data = msg
        if not data: 
            # workaround, status 204 does not work well
            data = ' '  
        if self.debug:
            if self.debug_format:
                print "\nsend to client:", prettyPrint(msg)
            else:
                print "send to client:", msg
        self.out_buffer += self.SCOPE_MESSAGE_STP_1 % (
            getTimestamp(), 
            service, 
            command,
            status,
            tag,
            len(data), 
            data
            )
        self.timeout = 0
        if not sender == self:
            self.handle_write()
            
    # ============================================================
    # Implementations of the asyncore.dispatcher class methods 
    # ============================================================
    
    def writable(self):
        if self.timeout and time() > self.timeout and not self.out_buffer:
            if self in connections_waiting:
                connections_waiting.remove(self)
                if not self.command == "scope_message": 
                    print ">>> failed, wrong connection type in queue" 
                self.out_buffer += self.RESPONSE_TIMEOUT % getTimestamp()
            else:
                self.out_buffer += NOT_FOUND % getTimestamp()
            self.timeout = 0
        return bool(self.out_buffer)
        
    def handle_close(self):
        if self in connections_waiting:
            connections_waiting.remove(self)
        self.close()