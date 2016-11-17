#!/usr/bin/python

import ConfigParser
import logging
import os
import sys
from pushbullet import Pushbullet
import tempfile

config_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ppc.conf')

if not os.path.exists(config_file_path):
    sys.exit(1)

config = ConfigParser.SafeConfigParser({'comskip-ini-path' : os.path.join(os.path.dirname(os.path.realpath(__file__)), 'comskip.ini'), 'temp-root' : tempfile.gettempdir(), 'nice-level' : '0'})
config.read(config_file_path)

PB = config.get('Pushbullet', 'api_key')

### Pushbullet integration


try:
        pb = Pushbullet(PB)
except Exception:
        logger.error('Pushbullet API key has failed, continuting but no messages will be delivered.')

def pbpush(title,message):
    try:
        push = pb.push_note(sys.argv[0].split('/')[-1].rstrip('.py')+': '+title,message)
        return
    except Exception:
        logger.error('Pushbullet has failed, no messages delivered')
        return

