#!/usr/bin/env python
import argparse
from datetime import datetime
from fuzzywuzzy import fuzz
import unicodedata
from sklearn import linear_model
import numpy as np
import tempfile
import subprocess
import sys
import copy
import os
from bokeh.plotting import figure, output_file, show
from bokeh.models import HoverTool, ColumnDataSource
from translation import bing
import progressbar


MATCHER_MAX_TIME_DIFF =  10 * 60 # 10 minutes
MATCHER_MIN_SUBTITLE_LENGTH = 10
MATCHER_MIN_SCORE = 70
MOVIE_EXTENSIONS = [".mkv", ".mp4", ".avi"]


class SubtitleTrack:
    def __init__(self, file):
        self.file = file
        self.subtitles = []

        with open(file) as srt_file:
            content = srt_file.read().split('\n')

        def read_content():
            for line in content:
                yield line.replace("\r", "")

        content_gen = read_content()

        for line in content_gen:
            if line is '':
                break

            lines = [line]
            while True:
                l = next(content_gen)

                if l is '' and len(lines) >= 3:
                    self.subtitles.append(Subtitle(lines))
                    break
                else:
                    lines.append(l)

    def __str__(self):
        text = ""
        for subtitle in self.subtitles:
            text += str(subtitle) + "\n"
        return text

    def write(self, file_path):
        subtitles = copy.deepcopy(self.subtitles)

        # Remove subtitles that end on a negative time.
        subtitles = [s for s in subtitles if s.end > 0]

        # Set time to 0 when subtitle start at negative time.
        for subtitle in subtitles:
            if subtitle.start < 0:
                subtitle.start = 0

        # Reset the ids
        for i in range (0, len(subtitles)):
            subtitles[i].ID = i + 1

        # Write subtitle
        file = open(file_path, "w")
        for subtitle in subtitles:
            file.write(subtitle.srt_string())
            file.write("\n")

        file.close()


class Subtitle:
    def __init__(self, lines):
        self.ID = lines[0]

        def parse_time(time):
            time = time.replace(",",".").split(':')
            time_parsed = int(time[0]) * 3600
            time_parsed += int(time[1]) * 60
            time_parsed += float(time[2])
            return time_parsed

        time = lines[1].split(" --> ")
        self.start = parse_time(time[0])
        self.end = parse_time(time[1])

        self.text = []
        self.text_parsed = ""

        for i in range(2, len(lines)):
            line = lines[i]
            self.text.append(line)
            self.text_parsed += "%s " % line

        # Parse the text to be more fuzzy compare friendly.
        chars_to_remove = [ "</i>", "<i>", ".", ",", "!", "-", ":", '"', "?"]
        for char in chars_to_remove:
            self.text_parsed = self.text_parsed.replace(char, "")

        self.text_parsed = self.text_parsed.lower()
        self.text_parsed = self.text_parsed.strip()

    def __str__(self):
        return str({
            "ID": self.ID,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "text_parsed": self.text_parsed
        })

    def srt_string(self):
        string = "%s\n" % self.ID

        def seconds_to_string(seconds):
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            ms = "{:.3f}".format(s).split(".")[1]
            return "%02d:%02d:%02d,%s" % (h, m, s, ms)

        string += "%s --> %s\n" % (seconds_to_string(self.start), seconds_to_string(self.end))

        for t in self.text:
            string += "%s\n" % t

        return string


def find_matches(input_track, sync_track):
    matches = []

    for input_subtitle in input_track.subtitles:
        found_matches = []

        for sync_subtile in sync_track.subtitles:
            time_diff = abs(sync_subtile.start - input_subtitle.start)
            if time_diff <= MATCHER_MAX_TIME_DIFF and len(input_subtitle.text_parsed) > MATCHER_MIN_SUBTITLE_LENGTH:
                score = fuzz.ratio(sync_subtile.text_parsed,
                                   input_subtitle.text_parsed)

                if score >= MATCHER_MIN_SCORE:
                    found_matches.append((score, sync_subtile))

        if len(found_matches) is 1:
            matches.append((found_matches[0][0], input_subtitle, found_matches[0][1]))

    return matches


def plot_matches(matches, plot_file, coefficient, intercept):
    output_file(plot_file)
    p = figure()
    p.add_tools(HoverTool(tooltips=[("input", "@input"),("sync", "@sync")]))

    x = []
    y = []
    x_linear_regression = []
    y_linear_regression = []
    input = []
    sync = []

    for match in matches:
        x.append(match[1].start)
        y.append(match[1].start - match[2].start)
        input.append(str(match[1]))
        sync.append(str(match[2]))
        x_linear_regression.append(match[1].start)
        y_linear_regression.append((match[1].start * coefficient) + intercept)

    source = ColumnDataSource(data=dict(x=x, y=y, input=input, sync=sync))

    p.line('x', 'y', source=source)
    p.line(x_linear_regression, y_linear_regression, color='red')
    show(p)
    print("Saved plot to %s" % plot_file)


def calculate_linear_regression(matches):
    x = []
    y = []

    for match in matches:
        y.append(match[1].start - match[2].start)
        x.append(match[1].start)

    X = np.vander(x, 2)

    def calculate_ransac():
        try:
            model_ransac = linear_model.RANSACRegressor()
            model_ransac.fit(X, y)
            return model_ransac
        except:
            return calculate_ransac()

    iterations = 5
    coef = 0
    intercept = 0
    for i in range(iterations):
        model_ransac = calculate_ransac()
        coef += model_ransac.estimator_.coef_[0]
        intercept += model_ransac.estimator_.intercept_

    return (coef / iterations, intercept / iterations)


def sync_with_linear_regression(subtitle_track, coefficient, intercept):
    for subtitle in subtitle_track.subtitles:
        subtitle.start -= intercept
        subtitle.end -= intercept
        subtitle.start -= (subtitle.start * coefficient)
        subtitle.end -= (subtitle.end * coefficient)


def generate_subtitle(video_file):
    temp = tempfile.mkstemp(suffix=".srt")[1]
    print subprocess.check_output(['autosub','-o',temp,video_file])
    return SubtitleTrack(temp)


def translate_text_parsed(subtitle_track, target_language):
    print('Translating...')
    bar = progressbar.ProgressBar()
    for i in bar(range(len(subtitle_track.subtitles))):
        try:
            subtitle = subtitle_track.subtitles[i]
            subtitle.text_parsed = bing(subtitle.text_parsed, dst = 'nl').encode('utf-8','ignore')
        except:
            print('Failed to translate %s' % (str(subtitle)))


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('-i', '--input', required=True,
                        help="Path to the subtitle to synchronize.")
    parser.add_argument('-s', '--sync', required=True,
                        help="Path to the video or subtitle to synchronize the input with.")
    parser.add_argument('-o', '--output', required=True,
                        help="Output path for the synchronized subtitle.")
    parser.add_argument('-p', '--plot',
                        help="Output path to save a plot (html) of the matches.")
    parser.add_argument('-l', '--lang',
                        help="If you --sync with subtitle provide the language of the --input subtitle. See languages.txt to find the language code (E.G. nl).")
    args = parser.parse_args()

    sync_extension = os.path.splitext(args.sync)[1].lower()
    if sync_extension == '.srt':
        if not args.lang:
            print('Missing --lang, provide the language of --input.')
            return 1

        print("Sync input with subtitle.")
        input_track = SubtitleTrack(args.input)
        sync_track = SubtitleTrack(args.sync)
        translate_text_parsed(sync_track, args.lang)
    elif sync_extension in MOVIE_EXTENSIONS:
        print("Sync input with movie.")
        input_track = SubtitleTrack(args.input)
        sync_track = generate_subtitle(args.sync)
    else:
        print("Unable to detect sync method, -s/--sync is in unsupported format.")
        return 1

    matches = find_matches(input_track, sync_track)

    if len(matches) is 0:
        print("Found no matches with sync input, unable to sync...")
        return 1

    (coefficient, intercept) = calculate_linear_regression(matches)

    if args.plot:
        plot_matches(matches, args.plot, coefficient, intercept)

    sync_with_linear_regression(input_track, coefficient, intercept)

    input_track.write(args.output)

    print("Wrote automatic synced subtitle file to %s" % args.output)

    return 0

if __name__ == '__main__':
    if sys.version_info >= (3, 0):
        print "Sorry, requires Python 2.x, not Python 3.x\n"
    	sys.exit(1)

    sys.exit(main())
