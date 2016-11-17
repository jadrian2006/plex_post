#!/usr/bin/python

import os
import psutil
import io
import sys
import logging
import json
import subprocess
import time
from pushbullet import Pushbullet
import ppcUtils
import ConfigParser
import tempfile
import uuid
import shutil

### Logging
#logger = logging.getLogger()
#handler = logging.StreamHandler()
#formatter = logging.Formatter('%(asctime)-5s %(levelname)-5s %(message)s')
#handler.setFormatter(formatter)
#logger.addHandler(handler)
#logger.setLevel(logging.DEBUG)


# sanity checks

config_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ppc.conf')
daemon_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ppc_daemon.py')

FFMPEG_PATH = "/usr/bin/ffmpeg"


### Starting Sanity - file checks


config = ConfigParser.SafeConfigParser({'comskip-ini-path' : os.path.join(os.path.dirname(os.path.realpath(__file__)), 'comskip.ini'), 'temp-root' : tempfile.gettempdir(), 'nice-level' : '0'})
config.read(config_file_path)
LOG_FILE_PATH = os.path.expandvars(os.path.expanduser(config.get('Logging', 'logfile-path')))
CONSOLE_LOGGING = config.getboolean('Logging', 'console-logging')
TEMP_ROOT = os.path.expandvars(os.path.expanduser(config.get('File Manipulation', 'temp-root')))


session_uuid = str(uuid.uuid4())
fmt = '%%(asctime)-15s [%s] %%(message)s' % session_uuid[:6]
if not os.path.exists(os.path.dirname(LOG_FILE_PATH)):
    os.makedirs(os.path.dirname(LOG_FILE_PATH))
logging.basicConfig(level=logging.DEBUG, format=fmt, filename=LOG_FILE_PATH)
if CONSOLE_LOGGING:
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

logging.debug('We have started the post_processor %s' % sys.argv)

if not os.path.exists(config_file_path):
    logging.error('Config file not found: %s' , config_file_path)
    logging.error('Make a copy of ppc.conf.example named ppc.conf, modify and place it in same directory as this script')
    sys.exit(1)


if not os.path.exists(daemon_file_path):
    logging.error('Please locate file %s, this is required to be in the same folder as this script.' , daemon_file_path)
    sys.exit(1)

### Input Checks

if len(sys.argv) < 2:
    print 'Usage: %s <video_file>' % os.path.basename(__file__)
    sys.exit(1)

if not os.path.exists(sys.argv[1]):
    print 'The file %s does not appear to be a valid file, please use a valid file.' % sys.argv[1]
    logging.error('The file %s does not apear valid, please use valid file.' , sys.argv[1])
    sys.exit(1)

cmd = '%s -i %s 2>&1 | grep \'Stream #0:0\'' % (FFMPEG_PATH, json.dumps(sys.argv[1]))
if not len(subprocess.check_output(cmd, shell=True)) > 0:
    print 'The file %s does not appear to be a valid video file, please use a valid video file.' % sys.argv[1]
    logging.error('The file %s does not appear to be a valid video file, please use a valid video file.' , sys.argv[1])
    sys.exit(1)

### We are going to check if we are in the .grab directory, if we are, we are going to copy to a temp dir otherwise plex will delete the file.

if str(sys.argv[1]).find('.grab') == -1:
    logging.debug('Our path is not in the .grab directory, should not be by plex_dvr')
    video = sys.argv[1]
else:
    logging.debug('Our path appears to be in the .grab directory')
    if not os.path.exists(os.path.join(TEMP_ROOT, 'working')):
        os.mkdir(os.path.join(TEMP_ROOT, 'working'), 0755)
        logging.debug('Our working directory doesnt exist, creating it %s' % os.path.join(TEMP_ROOT, 'working'))
    try:
        vid = sys.argv[1]
        logging.debug('Video 1 -> %s' % vid)
        working = os.path.join(TEMP_ROOT, 'working/')
        logging.debug('Video 2 -> %s' % working)
        video = os.path.join(working, os.path.basename(sys.argv[1]))
        logging.debug('Video 3 -> %s' % video)
        shutil.move(vid, working)
    except Exception, e:
        logging.error('Our move failed!!!')
        sys.exit(1)



### Lets check to see if our daemon is running and handle its trigger
ppc_daemon_pid = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ppc_daemon_pid')
ppc_queue_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ppc_queue_file')
ppc_queue_file_lockfile = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ppc_queue_file.lockfile')

def queue( movie ):
    logging.debug('FUNC:queue - Start')
    i = 0
    while os.path.exists(ppc_queue_file_lockfile):
        if i < 6:
            logging.info('queue is locked, waiting 2 seconds to try again - total lock time [ %s ] seconds' , i * 2)
            time.sleep(2)
            i = i + 1
        else:
            logging.error('Queue has been locked for 10 seconds, something is wrong, exiting!')
            sys.exit(1)

    with open(ppc_queue_file, "a+") as queue_file:
        a = str(movie+'\n')
        b = queue_file.readlines()
        if not b.count(str(a)) > 0:
            logging.info('queue_file does not have %s adding it.' , movie)
            queue_file.write(str(movie+'\n'))
            ppcUtils.pbpush('Queue_Add' , movie.split('/')[-1])
        else:
            logging.info('Our video %s already exists %s time(s), not adding it again' , a.rstrip('\n'),b.count(str(a)))


if not os.path.exists(ppc_daemon_pid):
    ### PID Doesnt exist, lets queue up a file, and then spawn daemon.
    if not os.path.exists(ppc_daemon_pid):
        logging.info('ppc_daemon is not running, lets spawn one.')
        if not os.path.exists(ppc_queue_file):
            logging.info('ppc_queue_file does not exist, lets create one.')
            queue(video)
            subprocess.Popen(daemon_file_path)
        else: 
            logging.debug('ppc_queue_file exists, lets check if %s exists.' , video)
            queue(video)
            subprocess.Popen(daemon_file_path)
else: 
    logging.debug('Our ppd_daemon_pid file exists, lets check if our proccess is running')
    with open(ppc_daemon_pid) as pid_file:
        pid_file = pid_file.readlines()
        pids = psutil.pids()
        logging.debug('Our PID File contents are: %s' , pid_file)
        logging.debug('Our PID File length is: %s' , int(len(pid_file)))
        if int(len(pid_file)) == 1:
            logging.debug('PID file not empty, lets see if our PID %s is running', pid_file[0].rstrip('\n'))
            active = int(pid_file[0].rstrip('\n'))

            if pids.count(active) == 1 :
                logging.debug('Great our Pid is active, but is it our daemon')
                p = psutil.Process(active)
                logging.debug('Command line of our active process %s is %s' , active,p.cmdline()[-1])
                logging.debug('Process name (via p.cmdline()) %s' , p.cmdline()[-1])
                logging.debug('Our daemon file name via path is %s' , daemon_file_path)
                if p.cmdline().count(daemon_file_path) == 1:
                    logging.debug('The name of our process is %s which is our daemon lets process queue', p.cmdline()[-1]) 
                    if not os.path.exists(ppc_queue_file):
                        logging.error('odd ppc_queue_file does not exist, yet our daemon is running')
                        sys.exit(1)
                    else:
                        queue(video)

            elif pids.count(active) == 0:
                logging.info('We have a pid, but no corresponding process, lets trigger the daemon again')
                queue(video)
                subprocess.Popen(daemon_file_path)

            else:
                logging.error('OPPS, something major broke, we have more than one active process with PID %s' , active)
                sys.exit(1)

            
        elif int(len(pid_file)) > 1:
            logging.debug('We have to many PIDS in our pid file something is not right')
            sys.exit(1)

        elif int(len(pid_file)) == 0: 
            logging.debug('We have a PID file, but no active PIDS')
            queue(video)
            subprocess.Popen(daemon_file_path)
