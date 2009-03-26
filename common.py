"""Common modules, constants, variables and function 
for the scope proxy / server

Overview:

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

__version__ = 0.8

import socket
import asyncore
import os
import re
import string
import sys
import time
import codecs
from time import gmtime, strftime, mktime, strptime, time
from calendar import timegm
from os import stat, listdir
from os.path import isfile, isdir
from os.path import exists as path_exists
from os.path import join as path_join
from os.path import sep as OS_PATH_SEP
from urllib import quote, unquote

CRLF = '\r\n'
BLANK = ' '
BUFFERSIZE = 8192
RE_HEADER = re.compile(": *")

RESPONSE_BASIC = \
    'HTTP/1.1 %s %s' + CRLF + \
    'Date: %s' + CRLF + \
    'Server: Dragonkeeper/%s' % __version__ + CRLF + \
    '%s'

# RESPONSE_OK_CONTENT % (timestamp, additional headers or empty, mime, content)
#
# HTTP/1.1 200 OK
# Date: %s
# Server: Dragonkeeper/0.8
# %sContent-Type: %s  
# Content-Length: %s
# 
# %s

RESPONSE_OK_CONTENT = RESPONSE_BASIC % (
    200,
    'OK',
    '%s',
    '%s' + \
    'Content-Type: %s' + CRLF + \
    'Content-Length: %s' + 2 * CRLF + \
    '%s'
)

# NOT_MODIFIED % ( timestamp )
# HTTP/1.1 304 Not Modified
# Date: %s
# Server: Dragonkeeper/0.8

NOT_MODIFIED = RESPONSE_BASIC % (
    304,
    'Not Modified',
    '%s',
    CRLF
)

# REDIRECT % ( timestamp, uri)
# HTTP/1.1 301 Moved Permanently
# Date: %s
# Server: Dragonkeeper/0.8
# Location: %s

REDIRECT = RESPONSE_BASIC % (
    301,
    'Moved Permanently',
    '%s',
    'Location: %s' + 2 * CRLF
)

# NOT_FOUND % ( timestamp )
# HTTP/1.1 404 NOT FOUND
# Date: %s
# Server: Dragonkeeper/0.8

NOT_FOUND = RESPONSE_BASIC % (
    404, 
    'NOT FOUND',
    '%s',
    'Content-Length:0' + 2 * CRLF 
)



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
RESPONSE_OK_CONTENT = RESPONSE_BASIC % (
    200,
    'OK',
    '%s',
    '%s' + \
    'Content-Type: %s' + CRLF + \
    'Content-Length: %s' + 2 * CRLF + \
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

# The template to create a html directory view
DIR_VIEW = \
"""
<!doctype html>
<html>
<head>
<title> </title>
<style>
  body 
  {
    font-family: "Lucida Sans Unicode", sans-serif;
    font-size: .8em;
  }
  ul 
  {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li 
  {
    padding-left: 0;
  }
  a 
  {
    text-decoration: none;
  }
  icon
  {
    display: inline-block;
    background-repeat: no-repeat;
    vertical-align: middle;
    width: -o-skin;
    height: -o-skin;
    margin-right: 3px;
  }
  .directory icon
  {
    background-image: -o-skin('Folder');
  }
  .file icon
  {
    background-image: -o-skin('Window Document Icon');
  }   
</style>
</head>
<body>
<ul>%s</ul>
</body>
</html>
"""
    
ITEM_DIR = """<li class="directory"><a href="./%s/"><icon></icon>%s</a></li>"""
ITEM_FILE = """<li class="file"><a href="./%s"><icon></icon>%s</a></li>"""

# scope scpecific markup
SERVICE_LIST = """<services>%s</services>"""
SERVICE_ITEM = """<service name="%s"/>"""
XML_PRELUDE = """<?xml version="1.0"?>%s"""
TIMEOUT = 30

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

def webURIToSystemPath(path):
    return path_join(*[unquote(part) for part in path.split('/')])

def systemPathToWebUri(path):
    return "/".join([quote(part) for part in path.split(OS_PATH_SEP)])

def getTimestamp(path = None):
    return strftime("%a, %d %b %Y %H:%M:%S GMT", 
                            gmtime(path and stat(path).st_mtime or None))

def timestampToTime(stamp):
    """see http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html#sec3.3.1 
    only this format is supported: Fri, 16 Nov 2007 16:09:43 GMT
    from the spec:
    HTTP applications have historically allowed three different formats 
    for the representation of date/time stamps: 
      Sun, 06 Nov 1994 08:49:37 GMT  ; RFC 822, updated by RFC 1123
      Sunday, 06-Nov-94 08:49:37 GMT ; RFC 850, obsoleted by RFC 1036
      Sun Nov  6 08:49:37 1994       ; ANSI C's asctime() format"""
    return timegm(strptime(stamp, "%a, %d %b %Y %H:%M:%S %Z"))

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
    except:
        pass
    return "".join(ret)

def prettyPrint(stp_1_msg):
    # TODO? pretty print data
    service, command, status, type, cid, tag, data = stp_1_msg 
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

class Options(object):
    #todo: subclass dict
    def __init__(self, *args, **kwargs):
        for arg in args:
            for key, val in arg.iteritems():
                self.__dict__[key]=val
            
    def __getitem__(self, name):
        return self.__dict__[name]
        
    def __getattr__(self, name):
        return self.__dict__[name]
        
    def __setitem__(self, name, value):
        self.__dict__[name]=value

    def __setattr__(self, name, value):
        self.__dict__[name]=value
    
    def __delattr__(self, name):
        del self.__dict__[name]
        
    def __deltitem__(self, name):
        del self.__dict__[name]

    def __str__(self):
        return str(self.__dict__)
        

class FileObject(object):
    def write(self, str):
        pass
    def read(self):
        pass
    def flush(self):
        pass

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
