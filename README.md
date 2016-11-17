PLEX_POST

Work In Progress:

This was intended to extend ekim1337's PlexComskip plex post processing script to add additional functionality.

Quick flow chart:

https://github.com/jadrian2006/plex_post/blob/master/Plex_Post.jpg

It consists of 2 primary worker files:

1: plex_post.py 
   - this is the file that you place in your plex_dvr post processor
     * 1: validates that the file passed to the plex_post is a valid video file
     * 2: queue processing
	- copies the file from .grab to your interstitial directory
	this prevents plex from deleting the file once the plex_post file ends before ppc_daemon finishes
	- watches for lock file to ensure that our queue is idle
	- updates queue with new file name
	- sends pushbullet message that a file was added to the queue
     * 3: Checks ppc_daemon status
        - check if ppc_daemon_pid file has a pid
	   -- has pid, checks to see if pid is running
	      if pid is running, checks to see if it is the ppc_daemon.py
	      if all is good, exit plex_post
           -- has pid, check to see if pid is running
              pid is not running, launch ppc_daemon.py
	   -- does not have a pid
              launch ppc_daemon.py
     * 4: exit plex_post

2: ppc_daemon.py
   - this is the actual worker for the plex_post processing
     * 1: loads queue file, extracts first video file
	- comskip processing
	- ffmpeg cut/merge processing
	- get resolution of the video and store it in its format (IE: 1080p, 480p, etc)
	- filebot rename with format : [Pure Genius - S01E01 - Pilot - 1080p.ts ] 
	- filebot during rename moves file to output folder - this is my sonaar drone factor path
	- sends pushbullet msg that the comskip process is done.

-----------------

Requirements:

sudo -H pip install psutil

sudo -H pip install pushbullet

filebot

ffmpeg

compskip

-- future handbrake -- 

-----------------

TODO:

- validate that NICE works, I modified the original PlexComskip quite heavily, and I do not use nice
- change nice to cpulimit to get better usage of processing
	* cpulimit will let you set a threadhold IE 50% or 75% of your system resources
- incorporate handbrake for encoding into H264 or H265 if 2160P format
	* will be limited with cpulimit
- clean up logging/debug logging to be more efficient and less chatty
- give options of which pushbullet messages you wish to see
- general optimzation / code efficiencies [this is a learning experience for me]
	* move more functions to the ppcUtils.py over embedded into the master scripts
	* add more optional components (ie, optional pushbullet, filebot, handbrake, versus hard code on)
- allow for custom comskip.ini based on video file name
- allow for custom renaming 
	* currently having problem with NCIS (2003)  -- it renames it to NCIS - New Orleans [grumble grumble]
- trigger library refresh on plex (not sure if possible) 
- open for suggestions!!
