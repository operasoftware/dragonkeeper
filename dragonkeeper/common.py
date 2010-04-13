# Copyright (c) 2008, Opera Software ASA
# license see LICENSE.

__version__ = '0.8.2'

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


class Options(object):
    #todo: subclass dict or userdict?
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


# Singleton class taken from
# http://book.opensourceproject.org.cn/lamp/python/pythoncook2/opensource/0596007973/pythoncook2-chp-6-sect-15.html

class Singleton(object):
    """ A Pythonic Singleton """

    def __new__(cls, *args, **kwargs):
        if '_inst' not in vars(cls):
            cls._inst = object.__new__(cls, *args, **kwargs)
        return cls._inst
"""
this is too hacky to be useful
def pretty_dragonfly_snapshot(in_string):
    # To pretty print dragonfly markup snapshots
    # hackybacky
    if in_string.startswith("<"):
        in_string = in_string.replace("'=\"\"", "")
        ret = []
        indent_count = 0
        INDENT = "  "
        LF = "\r\n"
        PROCESSING_INSTRUCTION = 0
        TEXT = 1
        TAG = 2
        CLOSING_TAG = 3
        OPENING_CLOSING_TAG = 4
        OPENING_TAG = 5
        matches_iter = re.finditer(r"(<\?[^>]*>)?([^<]*)(?:(<[^/][^>]*>)|(<\/[^>/]*>))", in_string)
        sp_sensitive = 0
        def check_sp_sensitivity(tag):
            for check in [
                        "spotlight-node", 
                        "class=\"pre-wrap\"",
                        "<property",
                        "<tab",
                        "<toolbar-filters",
                        "<toolbar-buttons",
                        "<toolbar-switches",
                        "<cst-select"


                    ]:
                if check in tag:
                    return True
            return False

        def skip(tag):
            for check in [
                        "<script", 
                    ]:
                if check in tag:
                    return True
            return False

        try:
            while True:
                m = matches_iter.next()
                matches = m.groups()
                if sp_sensitive:
                    if matches[CLOSING_TAG]:
                        sp_sensitive -= 1
                        last_match = CLOSING_TAG
                    elif "/>" in matches[TAG] or "<![CDATA[" in matches[TAG]:
                        last_match = OPENING_CLOSING_TAG
                    else:
                        sp_sensitive += 1
                        last_match = OPENING_TAG
                    ret.append(m.group())
                else:
                    if matches[CLOSING_TAG]:
                        
                        if last_match == OPENING_TAG:
                            ret.append(m.group().rstrip("\r\n \t"))
                            indent_count -= 1
                        else:
                            if matches[TEXT].strip("\r\n \t"):
                                ret.extend([LF, indent_count * INDENT, matches[TEXT].strip("\r\n \t")])
                            indent_count -= 1
                            ret.extend([LF, indent_count * INDENT, matches[CLOSING_TAG].strip("\r\n \t")])
                        last_match = CLOSING_TAG
                    elif "/>" in matches[TAG] or \
                        "<!--" in matches[TAG] or \
                        "<![CDATA[" in matches[TAG]:
                        last_match = OPENING_CLOSING_TAG
                        if not skip(matches[TAG]):
                            ret.extend([LF, indent_count * INDENT, m.group().strip("\r\n \t")])
                    else:
                        last_match = OPENING_TAG
                        if matches[PROCESSING_INSTRUCTION]:
                            ret.extend([indent_count * INDENT, matches[PROCESSING_INSTRUCTION].strip("\r\n \t")])
                        if matches[TEXT].strip("\r\n \t"):
                            ret.extend([LF, indent_count * INDENT, matches[TEXT].strip("\r\n \t")])
                        ret.extend([LF, indent_count * INDENT, matches[TAG].strip("\r\n \t")])
                        if check_sp_sensitivity(matches[TAG]):
                            sp_sensitive += 1
                        else:
                            indent_count += 1
        except StopIteration:
            pass
        except:
            raise
    else:
        ret = [in_string]
    return "".join(ret)
"""
