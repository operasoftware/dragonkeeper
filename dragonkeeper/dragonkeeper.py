import sys
import os
import socket
import argparse
import asyncore
from httpscopeinterface import HTTPScopeInterface
from stpconnection import ScopeConnection
from simpleserver import SimpleServer, asyncore
from upnpsimpledevice import SimpleUPnPDevice

if sys.platform == "win32":
    import msvcrt
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)

def _get_IP():
    ip = None
    hostname, aliaslist, ips = socket.gethostbyname_ex(socket.gethostname())
    while ips and ips[0].startswith("127."):
        ips.pop(0)
    if len(ips) == 1:
        ip = ips[0]
    else:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("opera.com", 80))
            ip = s.getsockname()[0]
            s.close()
        except:
            pass
    return ip

def _parse_args():
    parser = argparse.ArgumentParser(description="""
                                     Developper tool for Opera Dragonfly.
                                     Translates STP to HTTP.
                                     Exit: Control-C""")
    parser.add_argument("-d", "--debug",
                        action="store_true",
                        default=False,
                        help="print message flow")
    parser.add_argument("--only-errors",
                        action="store_true",
                        default=False,
                        help="print only error messages")
    parser.add_argument("-f", "--format",
                        action="store_true",
                        default=False,
                        help = "pretty print message flow")
    parser.add_argument("-j", "--format-payload",
                        action="store_true",
                        default=False,
                        help = "pretty print the message payload. can be very expensive")
    parser.add_argument("-r", "--root",
                        default=".",
                        help="the root directory of the server (default: %(default)s))")
    parser.add_argument("-p", "--proxy-port",
                        type=int,
                        default=7001,
                        dest="stp_port",
                        help = "STP port (default: %(default)s))")
    parser.add_argument("-s", "--server-port",
                        type=int,
                        default=8002,
                        dest="server_port",
                        help="server port (default: %(default)s))")
    parser.add_argument("--host",
                        default="0.0.0.0",
                        dest="host",
                        help="host (default: %(default)s))")
    parser.add_argument("-t", "--timing",
                        dest="is_timing",
                        default=False,
                        action="store_true",
                        help="timing between sending commands and receiving rsponses")
    parser.add_argument("--force-stp-0",
                        action = "store_true",
                        default=False,
                        help="force STP 0 protocol")
    parser.add_argument("--print-command-map",
                        action="store_true",
                        default=False,
                        dest="print_message_map",
                        help="print the command map")
    parser.add_argument("--print-command-map-services",
                        dest = "print_message_map_services",
                        default="",
                        help="""a comma separated list of services to print
                                the command map (default: %(default)s))""")
    parser.add_argument("--message-filter",
                        dest="message_filter",
                        default="",
                        help="""Filter the printing of the messages.
                                The argument is the filter or a path to a file with the filter.
                                If the filter is set, only messages which are
                                listed in the filter will be printed.
                                The filter uses JSON notation like:
                                {"<service name>": {"<message type>": [<message>*]}}",
                                with message type one of "command", "response", "event."
                                 '*' placeholder are accepted in <message>,
                                e.g. a filter to log all threads may look like:
                                 "{'ecmascript-debugger': {'event': ['OnThread*']}}".""")
    parser.add_argument("-v", "--verbose",
                        action="store_true",
                        default=False,
                        dest="verbose_debug",
                        help="print verbose debug info")
    parser.add_argument("--cgi",
                        action="store_true",
                        default=False,
                        dest="cgi_enabled",
                        help="enable cgi support")
    parser.add_argument("--servername",
                        default="localhost",
                        dest="SERVER_NAME",
                        help="server name (default: %(default)s))")
    parser.add_argument("--timeout",
                        type=float,
                        default=0.1,
                        dest="poll_timeout",
                        help="timeout for asyncore.poll (default: %(default)s))")
    parser.set_defaults(ip=_get_IP(), http_get_handlers={})
    return parser.parse_args()

def _run_proxy(args, count=None):
    server = SimpleServer(args.host, args.server_port, HTTPScopeInterface, args)
    args.SERVER_ADDR, args.SERVER_PORT = server.socket.getsockname()
    SimpleServer(args.host, args.stp_port, ScopeConnection, args)
    print "server on: http://%s:%s/" % (args.SERVER_NAME, args.SERVER_PORT)
    upnp_device = SimpleUPnPDevice(args.ip, args.server_port, args.stp_port)
    upnp_device.notify_alive()
    args.http_get_handlers["upnp_description"] = upnp_device.get_description
    args.upnp_device = upnp_device
    asyncore.loop(timeout=args.poll_timeout, count=count)

def main_func():
    args = _parse_args()
    if not args.ip:
        print "failed to get the IP of the machine"
        return
    if not os.path.isdir(args.root):
        parser.error("""Root directory "%s" does not exist""" % args.root)
        return
    if args.message_filter:
        from utils import MessageMap
        MessageMap.set_filter(args.message_filter)
    os.chdir(args.root)
    try:
        _run_proxy(args)
    except KeyboardInterrupt:
        args.upnp_device.notify_byby()
        asyncore.loop(timeout = 0.1, count=6)
        for fd, obj in asyncore.socket_map.items():
            obj.close()
        sys.exit()

if __name__ == "__main__":
    main_func()
