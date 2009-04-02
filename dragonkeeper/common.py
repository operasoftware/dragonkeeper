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

# NOT_FOUND % ( timestamp, content-length, content )
# HTTP/1.1 404 NOT FOUND
# Date: %s
# Server: Dragonkeeper/0.8
# Content-Type: text/plain  
# Content-Length: %s
# 
# %s

NOT_FOUND = RESPONSE_BASIC % (
    404, 
    'NOT FOUND',
    '%s',
    'Content-Type: text/plain' + CRLF + \
    'Content-Length:%s' + 2 * CRLF + \
    '%s'
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

TIMEOUT = 30

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
