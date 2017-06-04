# Autosub-sync
### Automatic synchronization of subtitles.

Autosub-sync is a utility for automatic synchronization of subtitles.

It provides two methods to synchronize your subtitles:
1. **Using a video**: this synchronizes your subtitle according to the video file.
   It uses speech recognition to generate a subtitle of the video file using: [agermanidis/autosub](https://github.com/agermanidis/autosub).
   Then your subtitle is synced with the generated subtitle.
   *Note: currently only English movies and subtitles are supported for this method.*
2. **Using a subtitle**: this synchronizes a subtitle in any language with an
   English subtitle. The English subtitle is translated to the language of your subtitle.
   Then your subtitle is synced with the translated subtitle.


### Installation

1. Install [ffmpeg](https://www.ffmpeg.org/).
2. Run `git clone https://github.com/Koenkk/autosub-sync.git autosub-sync`.
3. `cd autosub-sync`
4. `pip install -r requirements.txt`

### Usage

```
$ python autosub-sync.py -h
usage: autosub-sync.py [-h] -i INPUT -s SYNC -o OUTPUT [-p PLOT] [-l LANG]

optional arguments:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        Path to the subtitle to synchronize.
  -s SYNC, --sync SYNC  Path to the video or subtitle to synchronize the input
                        with.
  -o OUTPUT, --output OUTPUT
                        Output path for the synchronized subtitle.
  -p PLOT, --plot PLOT  Output path to save a plot (html) of the matches.
  -l LANG, --lang LANG  If you --sync with subtitle provide the language of
                        the --input subtitle.
```

### License

MIT
