#!/usr/bin/env python
import argparse
from datetime import datetime
from fuzzywuzzy import fuzz
from sklearn import linear_model
import numpy as np
import tempfile
import subprocess
import sys
import copy
from bokeh.plotting import figure, output_file, show
from bokeh.models import HoverTool, ColumnDataSource


MATCHER_MAX_TIME_DIFF =  10 * 60 # 10 minutes
MATCHER_MIN_SUBTITLE_LENGTH = 10
MATCHER_MIN_SCORE = 80


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

                if l is '':
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


def plot_matches(matches, plot_file):
    output_file(plot_file)
    p = figure()
    p.add_tools(HoverTool(tooltips=[("input", "@input"),("sync", "@sync")]))

    x = []
    y = []
    input = []
    sync = []

    for match in matches:
        x.append(match[1].start)
        y.append(match[1].start - match[2].start)
        input.append(str(match[1]))
        sync.append(str(match[2]))

    source = ColumnDataSource(data=dict(x=x, y=y, input=input, sync=sync))

    p.line('x', 'y', source=source)
    show(p)
    print("Saved plot to %s" % plot_file)


def calculate_linear_regression(matches):
    x = []
    y = []

    for match in matches:
        y.append(match[1].start - match[2].start)
        x.append(match[1].start)

    X = np.vander(x, 2)
    model_ransac = linear_model.RANSACRegressor(linear_model.LinearRegression())
    model_ransac.fit(X, y)
    return (model_ransac.estimator_.coef_[0], model_ransac.estimator_.intercept_)


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


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('-s', '--subtitle', required=True,
                        help="Path to the subtitle to synchronize.")
    parser.add_argument('-i', '--input', required=True,
                        help="Path to the video to synchronize the subtitle with.")
    parser.add_argument('-o', '--output', required=True,
                        help="Output path for the synchronized subtitle.")
    parser.add_argument('-p', '--plot',
                        help="Output path to save a plot (html) of the matches.")

    args = parser.parse_args()

    input_track = SubtitleTrack(args.subtitle)
    sync_track = generate_subtitle(args.input)

    matches = find_matches(input_track, sync_track)

    if args.plot:
        plot_matches(matches, args.plot)

    (coefficient, intercept) = calculate_linear_regression(matches)

    sync_with_linear_regression(input_track, coefficient, intercept)

    input_track.write(args.output)

    print("Wrote automatic synced subtitle file to %s" % args.output)

    return 0

if __name__ == '__main__':
    if sys.version_info >= (3, 0):
        print "Sorry, requires Python 2.x, not Python 3.x\n"
    	sys.exit(1)

    sys.exit(main())
