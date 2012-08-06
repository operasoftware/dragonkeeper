# Dragonkeeper - Opera Dragonfly development proxy

## Introduction

Dragonkeeper is a utility designed to ease development of Opera Dragonfly.

Dragonkeeper serves as a proxy between the Dragonfly client and a host (an Opera instance). This makes
it possible to run Dragonfly as a normal web page which makes development easier, e.g. by making it easy
to reload whenever changes are made, and also by allowing Dragonfly to be inspected by another Dragonfly
instance.

## Install

For installing, you need 'setuptools'.

    % python setup.py install

On Windows, you might want to add the install path to your PATH environment variable.

Note: Dragonkeeper doesn't have to be installed, but this is preferred.

## Usage

If installed:

    % dragonkeeper

if not installed:

    % python /path/to/dragonkeeper

Exit: Control-C

## Howto

Basic workflow when using Dragonkeeper is as follows:

- Get the Opera Dragonfly source from <https://github.com/operasoftware/dragonfly>

- Open a terminal, go to the `src` directory in Dragonfly's directory and run dragonkeeper:

        % cd path/to/dragonfly/src
        % dragonkeeper

  This should result in:

        server on: http://localhost:8002/
        
- Open <http://localhost:8002/client-en.xml> in Opera. There
  should be a message saying "Waiting for host connection on port 0".

- Open another instance of Opera from within your terminal using

        % opera -pd <profile-dir>

  `<profile-dir>` can simply be a temporary directory, e.g. `/tmp`.

  Alternatively, use another installation of Opera (as long as they have different profile directories).

- In the new Opera intance, go to [opera:debug](opera:debug), select port 7001 and click 'Connect'.

- Opera Dragonfly should now load in the first Opera instance. If not, reload it manually. You should
  also see some output from Dragonkeeper in the terminal.

The Dragonfly instance running in the normal browser window can now be itself be debugged by Opera
Dragonfly.

## Advanced

Settings: an optional file `CONFIG` overrides the defaults.
The options file is a standard .ini file, with a single section called
"dragonkeeper":

    [dragonkeeper]
    host:
    root: .
    server_port: 8002
    proxy_port: 7001
    debug: False
    format: False

### Options
```
  -h, --help            show this help message and exit
  -c CONFIG_PATH, --config=CONFIG_PATH
                        Path to config file
  -d, --debug           print message flow
  -f, --format          pretty print message flow
  -j, --format-payload  pretty print the message payload. can be very
                        expensive
  -r ROOT, --root=ROOT  the root directory of the server; default .
  -p PROXY_PORT, --proxy-port=PROXY_PORT
                        proxy port; default 7001
  -s SERVER_PORT, --server-port=SERVER_PORT
                        server port; default 8002
  --host=HOST           host; default localhost
  -i, --make-ini        Print a default dragonkeeper.ini and exit
  --force-stp-0         force stp 0 protocol
  --print-command-map   print the command map
  --message-filter=MESSAGE_FILTER
                        Filter the printing of the messages. The argument is
                        the filter or a path to a file with the filter. If the
                        filter is set, only messages which are listed in the
                        filter will be printed. The filter uses JSON notation
                        like: {"<service name>": {"<message type>":
                        [<message>*]}}", with message type one of "command",
                        "response", "event."  '*' placeholder are accepted in
                        <message>, e.g. a filter to log all threads may look
                        like:  "{'ecmascript-debugger': {'event':
                        ['OnThread*']}}".
  -v, --verbose         print verbose debug info
  --cgi                 enable cgi support
```


More comments in the source files.

## Changelog

See the `CHANGELOG` file

## Contact

Dragonkeeper is maintained by the Opera Dragonfly team. The authors are

- Christian Krebs <chrisk@opera.com>
- Rune Halvorsen
- Jan Borsodi <jborsodi@opera.com>

The Opera Dragonfly web site is at http://dragonfly.opera.com


## License

See the `LICENSE` file in the top distribution directory.

