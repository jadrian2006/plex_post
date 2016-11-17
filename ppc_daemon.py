#!/usr/bin/python
import os
import time
import psutil
import sys
import ConfigParser
import logging
import shutil
import subprocess
import tempfile
import uuid
import re
import json
import ppcUtils


#logger = logging.getLogger()
#handler = logging.StreamHandler()
#formatter = logging.Formatter('%(asctime)-5s %(levelname)-5s %(message)s')
#handler.setFormatter(formatter)
#logger.addHandler(handler)
#logger.setLevel(logging.DEBUG)


config_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ppc.conf')

config = ConfigParser.SafeConfigParser({'comskip-ini-path' : os.path.join(os.path.dirname(os.path.realpath(__file__)), 'comskip.ini'), 'temp-root' : tempfile.gettempdir(), 'nice-level' : '0'})
config.read(config_file_path)
LOG_FILE_PATH = os.path.expandvars(os.path.expanduser(config.get('Logging', 'daemon-logfile-path')))
CONSOLE_LOGGING = config.getboolean('Logging', 'console-logging')

COMSKIP_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'comskip-path')))
COMSKIP_INI_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'comskip-ini-path')))
FFMPEG_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'ffmpeg-path')))
TEMP_ROOT = os.path.expandvars(os.path.expanduser(config.get('File Manipulation', 'temp-root')))
COPY_ORIGINAL = config.getboolean('File Manipulation', 'copy-original')
SAVE_ALWAYS = config.getboolean('File Manipulation', 'save-always')
SAVE_FORENSICS = config.getboolean('File Manipulation', 'save-forensics')
NICE_LEVEL = config.get('Helper Apps', 'nice-level')
SEASON_OUTPUT_DIR = os.path.expandvars(os.path.expanduser(config.get('Output', 'season-output-path')))
MOVIE_OUTPUT_DIR = os.path.expandvars(os.path.expanduser(config.get('Output', 'movie-output-path')))
FILEBOT_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'filebot-path')))

session_uuid = str(uuid.uuid4())
fmt = '%%(asctime)-15s [%s] %%(message)s' % session_uuid[:6]
if not os.path.exists(os.path.dirname(LOG_FILE_PATH)):
    os.makedirs(os.path.dirname(LOG_FILE_PATH))

logging.basicConfig(level=logging.DEBUG, format=fmt, filename=LOG_FILE_PATH)
if CONSOLE_LOGGING:
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)

logging.debug('We have started the ppc_daemon %s' % sys.argv)


if not os.path.exists(config_file_path):
    logging.error('We cant find our config, odd as you passed the parent check')
    sys.exit(1)



ppc_daemon_pid = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ppc_daemon_pid')
ppc_queue_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ppc_queue_file')
ppc_queue_file_lockfile = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'ppc_queue_file.lockfile')

#################### 
## Human readable bytes.
def sizeof_fmt(num, suffix='B'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Y', suffix)

## Capture resolution of the video
def px_size2(movie):
    cmd = '%s -i %s 2>&1 | grep \'Stream #0:0\' | grep -oP \', \K[0-9]+x[0-9]+\'' % (FFMPEG_PATH, movie)
    size = subprocess.check_output(cmd, shell=True)
    size = size.split('x')
    res = {"2160" : "2160p" , "1080" : "1080p" , "720" : "720p" , "480" : "480p" , "360" : "360p"}
    if size in res:
        size = res[size]
        return size
    else:
        size = "sd"
        return size

def px_size (str):
    cmd = '%s -i %s 2>&1 | grep \'Stream #0:0\' | grep -oP \', \K[0-9]+x[0-9]+\'' % (FFMPEG_PATH, str)
    size = subprocess.check_output(cmd, shell=True)
    if '2160' in size:
        size = "2160p"
        return size
    elif '1080' in size:
        size = "1080p"
        return size
    elif '720' in size:
        size = "720p"
        return size
    elif '480' in size:
        size = "480p"
        return size
    elif '360' in size:
        size = "360p"
        return size
    else:
        size = "sd"
        return size

## Clean up after outselves and exit.
def cleanup_and_exit(temp_dir, keep_temp=False):
    if keep_temp:
        logging.info('Leaving temp files in: %s' % temp_dir)
    else:
        try:
            os.chdir(os.path.expanduser('~'))  # Get out of the temp dir before we nuke it (causes issues on NTFS)
            shutil.rmtree(temp_dir)
        except Exception, e:
            logging.error('Problem whacking temp dir: %s' % temp_dir)
            logging.error(str(e))

    ## Exit Cleanly.
    logging.info('Done processing!')
    sys.exit(0)

def proccessor(movie):
    session_uuid = str(uuid.uuid4())
    fmt = '%%(asctime)-15s [%s] %%(message)s' % session_uuid[:6]
    logging.info('FUNC_Proccessor start: Processing %s' , movie.rstrip('\n'))
    if not os.path.exists(movie.rstrip('\n')):
        logging.error('File in queue which does not exist, removing %s and continueing.' , movie.rstrip('\n'))
        return
    else:
        try:
            video_path = movie
            temp_dir = os.path.join(TEMP_ROOT, session_uuid)
            os.makedirs(temp_dir)
            os.chdir(temp_dir)

            logging.info('Using session ID: %s' % session_uuid)
            logging.info('Using temp dir: %s' % temp_dir)
            logging.info('Using input file: %s' % video_path)
            logging.info('Using Season Output Dir: %s' % SEASON_OUTPUT_DIR)
            logging.info('Using Movie Output Dir: %s' % MOVIE_OUTPUT_DIR)
            logging.info('Filebot Location: %s' % FILEBOT_PATH)

            original_video_dir = os.path.dirname(video_path)
            video_basename = os.path.basename(video_path)
            video_name, video_ext = os.path.splitext(video_basename)
        except Exception, e:
            logging.error('Something went wrong setting up temp paths and working files: %s' % e)
            sys.exit(0)
        try:
            if COPY_ORIGINAL or SAVE_ALWAYS:
                temp_video_path = os.path.join(temp_dir, video_basename)
                logging.info('Copying file to work on it: %s' % temp_video_path)
                shutil.copy(video_path, temp_dir)
            else:
                temp_video_path = video_path

            # Process with comskip.
            cmd = NICE_ARGS + [COMSKIP_PATH, '--output', temp_dir, '--ini', COMSKIP_INI_PATH, temp_video_path]
            logging.info('[comskip] Command: %s' % cmd)
            subprocess.call(cmd)
        except Exception, e:
            logging.error('Something went wrong during comskip analysis: %s' % e)
            cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)

        edl_file = os.path.join(temp_dir, video_name + '.edl')
        logging.info('Using EDL: ' + edl_file)
        try:
            segments = []
            prev_segment_end = 0.0
            if os.path.exists(edl_file):
                with open(edl_file, 'rb') as edl:

                    # EDL contains segments we need to drop, so chain those together into segments to keep.
                    for segment in edl:
                        start, end, something = segment.split()
                        if float(start) == 0.0:
                            logging.info('Start of file is junk, skipping this segment...')
                        else:
                            keep_segment = [float(prev_segment_end), float(start)]
                            logging.info('Keeping segment from %s to %s...' % (keep_segment[0], keep_segment[1]))
                            segments.append(keep_segment)
                        prev_segment_end = end
            # Write the final keep segment from the end of the last commercial break to the end of the file.
            keep_segment = [float(prev_segment_end), -1]
            logging.info('Keeping segment from %s to the end of the file...' % prev_segment_end)
            segments.append(keep_segment)

            segment_files = []
            segment_list_file_path = os.path.join(temp_dir, 'segments.txt')
            with open(segment_list_file_path, 'wb') as segment_list_file:
                for i, segment in enumerate(segments):
                    segment_name = 'segment-%s' % i
                    segment_file_name = '%s%s' % (segment_name, video_ext)
                    if segment[1] == -1:
                        duration_args = []
                    else:
                        duration_args = ['-t', str(segment[1] - segment[0])]
                    cmd = NICE_ARGS + [FFMPEG_PATH, '-i', temp_video_path, '-ss', str(segment[0])]
                    cmd.extend(duration_args)
                    cmd.extend(['-c', 'copy', segment_file_name])
                    logging.info('[ffmpeg] Command: %s' % cmd)
                    try:
                        subprocess.call(cmd)
                    except Exception, e:
                        logging.error('Something went wrong during splitting: %s' % e)
                        cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)
                    # If the last drop segment ended at the end of the file, we will have written a zero-duration file.
                    if os.path.exists(segment_file_name):
                        if os.path.getsize(segment_file_name) < 1000:
                            logging.info('Last segment ran to the end of the file, not adding bogus segment %s for concatenation.' % (i + 1))
                            continue

                        segment_files.append(segment_file_name)
                        segment_list_file.write('file %s\n' % segment_file_name)
        except Exception, e:
            logging.error('Something went wrong during splitting: %s' % e)
            cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)

        logging.info('Going to concatenate %s files from the segment list.' % len(segment_files))
        try:
            cmd = NICE_ARGS + [FFMPEG_PATH, '-y', '-f', 'concat', '-i', segment_list_file_path, '-c', 'copy', os.path.join(temp_dir, video_basename)]
            logging.info('[ffmpeg] Command: %s' % cmd)
            subprocess.call(cmd)
        except Exception, e:
            logging.error('Something went wrong during concatenation: %s' % e)
            cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)

        logging.info('Sanity checking our work...')
        try:
            input_size = os.path.getsize(video_path)
            output_size = os.path.getsize(os.path.join(temp_dir, video_basename))
            if input_size and 1.01 > float(output_size) / float(input_size) > 0.99:
                logging.info('Output file size was too similar (doesn\'t look like we did much); we won\'t replace the original: %s -> %s' % (sizeof_fmt(input_size), sizeof_fmt(output_size)))
                cleanup_and_exit(temp_dir, SAVE_ALWAYS)
            elif input_size and 1.1 > float(output_size) / float(input_size) > 0.5:
                logging.info('Output file size looked sane, we\'ll replace the original: %s -> %s' % (sizeof_fmt(input_size), sizeof_fmt(output_size)))
                # Check if we are a series, or a movie
                p = re.compile('[sS][0-9]+[eE][0-9]+')
                m = p.search(os.path.join(temp_dir, video_basename))
                if m:
                    logging.info('We are a series, filebot rename and moving file -> %s to %s' % (os.path.join(temp_dir, video_basename), SEASON_OUTPUT_DIR))
                    size = px_size(json.dumps(os.path.join(temp_dir, video_basename)))
                    logging.info('Debug Message: Filename %s and size %s' % (json.dumps(os.path.join(temp_dir, video_basename)),size))
                    file_path = json.dumps(os.path.join(temp_dir, video_basename))
                    logging.info('Debug Filebot_path: %s' % FILEBOT_PATH)
                    logging.info('Debug size: %s' % size)
                    logging.info('Debug File: %s' % (file_path))
                    logging.info('Debug Season Output DIR: %s' % SEASON_OUTPUT_DIR)
                    logging.info('Debug File2 %s' % (file_path))
                    fbcmd = '%s -rename -non-strict -no-xattr --db TheTVDB --format \"{n} - {s00e00} - {t} - %s\" --output %s %s' % (FILEBOT_PATH, size, SEASON_OUTPUT_DIR, file_path)
                    logging.info('fbcmd debug: %s' % (fbcmd))
                    subprocess.call(fbcmd, shell=True)
                else:
                    shutil.move(os.path.join(temp_dir, video_basename), MOVIE_OUTPUT_DIR)
                    cleanup_and_exit(temp_dir, SAVE_ALWAYS)
            else:
                logging.info('Output file size looked wonky (too big or too small); we won\'t replace the original: %s -> %s' % (sizeof_fmt(input_size), sizeof_fmt(output_size)))
                cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)
        except Exception, e:
            logging.error('Something went wrong during sanity check: %s' % e)
            cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)


# Set our own nice level and tee up some args for subprocesses (unix-like OSes only).
NICE_ARGS = []
if sys.platform != 'win32':
    try:
        nice_int = max(min(int(NICE_LEVEL), 20), 0)
        if nice_int > 0:
            os.nice(nice_int)
            NICE_ARGS = ['nice', '-n', str(nice_int)]
    except Exception, e:
        logging.error('Couldn\'t set nice level to %s: %s' % (NICE_LEVEL, e))



with open(ppc_daemon_pid, "a+") as pid_file:
    pids = pid_file.readlines()
    if int(len(pids)) == 0:
        pid_file.write(str(os.getpid())+'\n')
        pid_file.close()
    else:
        print "hmm.. we have a pid, better fix"
        print "going to exit"
        sys.exit(1)


with open(ppc_queue_file, "r+") as queue_file:
    movies = queue_file.readlines()
    i = len(movies)
    print 'Number of movies is %s' % i
    

while i > 0:
    logging.debug('Starting our worker process with movie %s' , movies[0])
    ## Calling our worker function 
    proccessor(movies[0].rstrip('\n'))

    logging.debug('Proccess function done, on %s, updating queue.' , movies[0].rstrip('\n'))
    ppcUtils.pbpush('Comskip_Finish',movies[0].rstrip('\n').split('/')[-1])

    with open(ppc_queue_file_lockfile, "a+") as queue_lockfile:
        with open(ppc_queue_file, "r") as queue_file:
            movies = queue_file.readlines()
            for line in movies:
                if str(line) != str(movies[0]):
                    queue_lockfile.write(line)
                else:
                    time.sleep(5)
    os.rename(ppc_queue_file_lockfile,ppc_queue_file)
    with open(ppc_queue_file, "r") as queue_file:
        movies = queue_file.readlines()
        i = len(movies)

logging.info('We have completed our work, existing clean')
f = open(ppc_daemon_pid, 'w')
f.close
sys.exit(0)
