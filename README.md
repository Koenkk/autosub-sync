# Autosub-sync
### Automatic synchronization of subtitles for any video.

Autosub-sync is a utility for automatic synchronization of English subtitles with English spoken video files.
It uses [agermanidis/autosub](https://github.com/agermanidis/autosub) to create a subtitle for the video and then syncs this subtitle with your English subtitle.


### Installation

1. Install [ffmpeg](https://www.ffmpeg.org/).
2. Run `git clone https://github.com/Koenkk/autosub-sync.git autosub-sync`.
3. `cd autosub-sync`
4. `pip install -r requirements.txt`

### Usage

```
$ python autosub-sync.py -h
usage: autosub-sync [-h] -s SUBTITLE -v VIDEO -o OUTPUT

optional arguments:
  -h, --help            show this help message and exit
  -s SUBTITLE, --subtitle SUBTITLE
                        Path to the subtitle to synchronize.
  -v VIDEO, --video VIDEO
                        Path to the video to synchronize the subtitle with.
  -o OUTPUT, --output OUTPUT
                        Output path for the synchronized subtitle.
```

### License

MIT
