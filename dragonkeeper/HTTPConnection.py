# Copyright (c) 2008, Opera Software ASA
# license see LICENSE.

import asyncore
import sys
from time import time
from os import stat, listdir
from os.path import isfile, isdir
from os.path import exists as path_exists
from os.path import join as path_join
from mimetypes import types_map
from common import *


class HTTPConnection(asyncore.dispatcher):
    """To provide a simple HTTP response handler.
    Special methods can be implementd by subclassing this class
    """

    def __init__(self, conn, addr, context):
        asyncore.dispatcher.__init__(self, sock = conn)
        self.addr = addr
        self.in_buffer = ""
        self.out_buffer = ""
        self.content_length = 0
        self.check_input = self.read_headers
        self.query = ''
        self.raw_post_data = ""
        # Timeout acts also as flag to signal
        # a connection which still waits for a response
        self.timeout = 0

    def read_headers(self):
        if 2*CRLF in self.in_buffer:
            # to dispatch any hanging timeout response
            self.flush()
            headers_raw, self.in_buffer = self.in_buffer.split(2*CRLF, 1)
            first_line, headers_raw = headers_raw.split(CRLF, 1)
            method, path, protocol = first_line.split(BLANK, 2)
            path = path.lstrip("/")
            if "?" in path:
                path, self.query = path.split('?', 1)
            self.headers = dict((RE_HEADER.split(line, 1)
                                    for line in headers_raw.split(CRLF)))
            arguments = path.split("/")
            command = arguments and arguments.pop(0) or ""
            command = command.replace('-', '_').replace('.', '_')
            self.method = method
            self.path = path
            self.command = command
            self.arguments = arguments
            self.timeout = time() + TIMEOUT
            handled = False
            # POST
            if method == "POST":
                if "Content-Length" in self.headers:
                    self.content_length = int(self.headers["Content-Length"])
                    self.check_input = self.read_content
                    self.check_input()
            # GET
            elif method == "GET":
                if hasattr(self, command) and hasattr(getattr(self, command), '__call__'):
                    getattr(self, command)()
                else:
                    system_path = URI_to_system_path(path.rstrip("/")) or "."
                    if os.path.exists(system_path) or not path:
                        self.serve(path, system_path)
                    elif path == "favicon.ico":
                        self.serve(path, path_join(SOURCE_ROOT, "favicon.ico"))
                    else:
                        content = "The server cannot handle: %s" % path
                        self.out_buffer += NOT_FOUND % (
                            get_timestamp(),
                            len(content),
                            content)
                        self.timeout = 0
                if self.in_buffer:
                    self.check_input()
            # Not implemented method
            else:
                content = "The server cannot handle: %s" % method
                self.out_buffer += NOT_FOUND % (
                    get_timestamp(),
                    len(content),
                    content)
                self.timeout = 0

    def read_content(self):
        if len(self.in_buffer) >= self.content_length:
            self.raw_post_data = self.in_buffer[0:self.content_length]
            if hasattr(self, self.command):
                getattr(self, self.command)()
            else:
                content = "The server cannot handle: %s" % self.path
                self.out_buffer += NOT_FOUND % (
                    get_timestamp(),
                    len(content),
                    content)
            self.raw_post_data = ""
            self.in_buffer = self.in_buffer[self.content_length:]
            self.content_length = 0
            self.check_input = self.read_headers
            if self.in_buffer:
                self.check_input()

    def serve(self, path, system_path):
        if path_exists(system_path) or path == "":
            if isfile(system_path):
                self.serve_file(path, system_path)
            elif isdir(system_path) or path == "":
                self.serve_dir(path, system_path)
        else:
            content = "The sever couldn't find %s" % system_path
            self.out_buffer += NOT_FOUND % (
                get_timestamp(),
                len(content),
                content)
            self.timeout = 0

    def serve_file(self, path, system_path):
        if "If-Modified-Since" in self.headers and \
           timestamp_to_time(self.headers["If-Modified-Since"]) >= \
           int(stat(system_path).st_mtime):
            self.out_buffer += NOT_MODIFIED % get_timestamp()
            self.timeout = 0
        else:
            ending = "." in path and path[path.rfind("."):] or "no-ending"
            mime = ending in types_map and types_map[ending] or 'text/plain'
            try:
                f = open(system_path, 'rb')
                content = f.read()
                f.close()
                self.out_buffer += RESPONSE_OK_CONTENT % (
                    get_timestamp(),
                    'Last-Modified: %s%s' % (
                        get_timestamp(system_path),
                        CRLF),
                    mime,
                    len(content),
                    content)
                self.timeout = 0
            except:
                content = "The server cannot find %s" % system_path
                self.out_buffer += NOT_FOUND % (
                    get_timestamp(),
                    len(content),
                    content)
                self.timeout = 0

    def serve_dir(self, path, system_path):
        if path and not path.endswith('/'):
            self.out_buffer += REDIRECT % (get_timestamp(), path + '/')
            self.timeout = 0
        else:
            try:
                items_dir = [item for item in listdir(system_path)
                                if isdir(path_join(system_path, item))]
                items_file = [item for item in listdir(system_path)
                                if isfile(path_join(system_path, item))]
                items_dir.sort()
                items_file.sort()
                if path:
                    items_dir.insert(0, '..')
                markup = [ITEM_DIR % (quote(item), item)
                            for item in items_dir]
                markup.extend([ITEM_FILE % (quote(item), item)
                                    for item in items_file])
                content = DIR_VIEW % ("".join(markup))
            except Exception, msg:
                content = DIR_VIEW % """<li style="color:#f30">%s</li>""" % msg
            self.out_buffer += RESPONSE_OK_CONTENT % (
                get_timestamp(),
                '',
                "text/html",
                len(content),
                content)
            self.timeout = 0
    # ============================================================
    # 
    # ============================================================
    def flush(self):
        pass
    # ============================================================
    # Implementations of the asyncore.dispatcher class methods
    # ============================================================
    def handle_read(self):
        self.in_buffer += self.recv(BUFFERSIZE)
        self.check_input()

    def writable(self):
        return bool(self.out_buffer)

    def handle_write(self):
        sent = self.send(self.out_buffer)
        self.out_buffer = self.out_buffer[sent:]

    def handle_close(self):
        self.close()
