__version__ = '0.8.3'

import socket
import asyncore
import os
import re
import string
import sys
import time
import codecs
from time import gmtime, strftime, mktime, strptime, time, daylight
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
RE_HEADER_LINES = re.compile(CRLF + "(?![ \t])")
SOURCE_ROOT = os.path.dirname(os.path.abspath(__file__))

def parse_headers(buffer):
    if 2*CRLF in buffer:
        headers_raw, buffer = buffer.split(2*CRLF, 1)
        first_line, headers = headers_raw.split(CRLF, 1)
        headers = dict((RE_HEADER.split(line, 1) for line in RE_HEADER_LINES.split(headers)))
        return (
            headers_raw + 2 * CRLF,
            first_line,
            headers,
            buffer
        )
    return None

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
    '%s')

# NOT_MODIFIED % ( timestamp )
# HTTP/1.1 304 Not Modified
# Date: %s
# Server: Dragonkeeper/0.8

NOT_MODIFIED = RESPONSE_BASIC % (
    304,
    'Not Modified',
    '%s',
    CRLF,
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
    'Location: %s' + 2 * CRLF,
)

# BAD_REQUEST % ( timestamp )
# HTTP/1.1 400 Bad Request
# Date: %s
# Server: Dragonkeeper/0.8

BAD_REQUEST = RESPONSE_BASIC % (
    400,
    'Bad Request',
    '%s',
    2 * CRLF,
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
    '%s',
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


def URI_to_system_path(path):
    return path_join(*[unquote(part) for part in path.split('/')])


def get_timestamp(path = None):
    return strftime("%a, %d %b %Y %H:%M:%S GMT",
                            gmtime(path and stat(path).st_mtime or None))

def get_ts_short():
    t = time()
    tint = int(t)
    return "%02d:%02d:%02d:%03d" % (((tint / (60 * 60)) + daylight) % 24,
                                    (tint / 60) % 60,
                                    tint % 60,
                                    (t - tint) * 1000)


def timestamp_to_time(stamp):
    """see http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html#sec3.3.1
    only this format is supported: Fri, 16 Nov 2007 16:09:43 GMT
    from the spec:
    HTTP applications have historically allowed three different formats
    for the representation of date/time stamps:
      Sun, 06 Nov 1994 08:49:37 GMT  ; RFC 822, updated by RFC 1123
      Sunday, 06-Nov-94 08:49:37 GMT ; RFC 850, obsoleted by RFC 1036
      Sun Nov  6 08:49:37 1994       ; ANSI C's asctime() format"""
    return timegm(strptime(stamp, "%a, %d %b %Y %H:%M:%S %Z"))

# Singleton class taken from
# http://book.opensourceproject.org.cn/lamp/python/pythoncook2/opensource/0596007973/pythoncook2-chp-6-sect-15.html

class Singleton(object):
    """ A Pythonic Singleton """

    def __new__(cls, *args, **kwargs):
        if '_inst' not in vars(cls):
            cls._inst = object.__new__(cls, *args, **kwargs)
        return cls._inst

class ProfileContext(object):
    def __init__(self, log_msg="", tolerance=.05):
        self.time = time()
        self.call_count = 0
        self.calls_per_sec = 0
        self.socket_count = 0
        self.log_msg = log_msg
        self.tolerance = tolerance

    def count(self):
        self.call_count += 1
        now = time()
        if now - self.time > 1:
            calls_per_sec = self.call_count * (1 / (now - self.time))
            self.call_count = 0
            self.time = now
            if calls_per_sec < self.calls_per_sec * (1 - self.tolerance) or \
               calls_per_sec > self.calls_per_sec * (1 + self.tolerance):
                self.calls_per_sec = calls_per_sec
                print self.log_msg, int(calls_per_sec)
