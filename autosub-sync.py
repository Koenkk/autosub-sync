#!/usr/bin/env python
import argparse
from fuzzywuzzy import fuzz
from sklearn import linear_model
import numpy as np
import subprocess
import sys
import os
from bokeh.plotting import figure, output_file, save
from bokeh.models import HoverTool, ColumnDataSource
from translation import bing
import progressbar
import pysrt
import logging
import copy

MATCHER_MAX_TIME_DIFF = 10 * 60  # 10 minutes
MATCHER_MIN_SUBTITLE_LENGTH = 10
MATCHER_MIN_SCORE = 70
VIDEO_EXTENSIONS = [".mkv", ".mp4", ".avi"]


def parse_time_str(sub_time):
    time = float(sub_time.milliseconds) / 1000
    time += sub_time.seconds
    time += sub_time.minutes * 60
    time += sub_time.hours * 3600
    return time


def remove_punc_from_str(text):
    chars = [".", ",", "!", "-", ":", '"', "?"]
    for char in chars:
        text = text.replace(char, "")
    return text


def find_matches(input_track, sync_track):
    matches = []
    input_track = [(s, parse_time_str(s.start),
                   remove_punc_from_str(s.text_without_tags))
                   for s in input_track]
    sync_track = [(s, parse_time_str(s.start),
                  remove_punc_from_str(s.text_without_tags))
                  for s in sync_track]

    for input_subtitle in input_track:
        found_matches = []

        for sync_subtitle in sync_track:
            time_diff = abs(sync_subtitle[1] - input_subtitle[1])
            if (time_diff <= MATCHER_MAX_TIME_DIFF and
               len(input_subtitle[2]) > MATCHER_MIN_SUBTITLE_LENGTH):
                score = fuzz.ratio(sync_subtitle[2], input_subtitle[2])

                if score >= MATCHER_MIN_SCORE:
                    found_matches.append((score, sync_subtitle[0]))

        if len(found_matches) is 1:
            matches.append((found_matches[0][0], input_subtitle[0],
                            found_matches[0][1]))

    return matches


def plot_matches(matches, plot_file, coefficient, intercept):
    output_file(plot_file)
    p = figure()
    p.add_tools(HoverTool(tooltips=[("input", "@input"), ("sync", "@sync")]))

    x = []
    y = []
    x_linear_regression = []
    y_linear_regression = []
    input = []
    sync = []

    for match in matches:
        x.append(parse_time_str(match[1].start))
        y.append(parse_time_str(
            match[1].start) - parse_time_str(match[2].start)
        )
        input.append(match[1].text)
        sync.append(match[2].text)
        x_linear_regression.append(parse_time_str(match[1].start))
        y_linear_regression.append((
            parse_time_str(match[1].start) * coefficient) + intercept
        )

    source = ColumnDataSource(data=dict(x=x, y=y, input=input, sync=sync))

    p.line('x', 'y', source=source)
    p.line(x_linear_regression, y_linear_regression, color='red')
    save(p)
    logging.info("Saved plot to %s" % plot_file)


def calculate_linear_regression(matches):
    x = []
    y = []

    for match in matches:
        y.append(parse_time_str(match[1].start) -
                 parse_time_str(match[2].start))
        x.append(parse_time_str(match[1].start))

    X = np.vander(x, 2)

    max_attempts = 3

    def calculate_ransac(attempts=0):
        if attempts is max_attempts:
            raise Exception("Failed to calculate_ransac.")

        try:
            model_ransac = linear_model.RANSACRegressor()
            model_ransac.fit(X, y)
            return model_ransac
        except Exception as e:
                return calculate_ransac(attempts + 1)

    iterations = 5
    coef = 0
    intercept = 0
    for i in range(iterations):
        model_ransac = calculate_ransac()
        coef += model_ransac.estimator_.coef_[0]
        intercept += model_ransac.estimator_.intercept_

    return (coef / iterations, intercept / iterations)


def sync_with_linear_regression(subtitle_track, coefficient, intercept):
    logging.info("Syncing with intercept %s and coefficient %s" %
                 (intercept, coefficient))
    subtitle_track = copy.deepcopy(subtitle_track)
    subtitle_track.shift(seconds=(intercept * -1))
    for subtitle in subtitle_track:
        subtitle.start -= {'seconds': parse_time_str(subtitle.start) *
                           coefficient}
        subtitle.end -= {'seconds': parse_time_str(subtitle.end) * coefficient}

    return subtitle_track


def execute_cmd(cmd):
    logging.info("Execute command: %s" % cmd)
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    for line in iter(process.stdout.readline, ''):
        if type(line) is not str:
            logging.info("Command executed")
            break

        sys.stdout.write(line)


def generate_subtitle(video_file, output):
    logging.info("Generating subtitle for: %s" % video_file)
    output = "%s.autosub.srt" % video_file
    execute_cmd(['autosub', '-o', output, video_file])
    return output


def translate_subtitle(subtitle_track, target_language):
    logging.info('Translating to %s' % (target_language))
    bar = progressbar.ProgressBar()
    for subtitle in bar(subtitle_track):
        try:
            text = str(remove_punc_from_str(subtitle.text_without_tags))
            subtitle.text = bing(text, dst='nl')
        except KeyboardInterrupt:
            sys.exit(1)
        except Exception as e:
            logging.error("Failed to translate part of subtitle :(")


def open_subtitle(file):
    try:
        return pysrt.open(file)
    except Exception as e:
        return pysrt.open(file, encoding='iso-8859-1')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-i', '--input', required=True,
        help="Path to the subtitle to synchronize.")
    parser.add_argument(
        '-s', '--sync', required=True,
        help="Path to the video or subtitle to synchronize the input with.")
    parser.add_argument(
        '-o', '--output', required=True,
        help="Output path for the synchronized subtitle.")
    parser.add_argument(
        '--debug', help="Save debug files.", action='store_true')
    parser.add_argument(
        '-l', '--lang',
        help=("If you --sync with subtitle provide the language of the --input"
              "subtitle. See languages.txt to find the language code"
              "(E.G. nl)."))
    args = parser.parse_args()

    logging.basicConfig(format='%(levelname)s - %(asctime)s: %(message)s',
                        datefmt='%m/%d/%Y %H:%M:%S', level=logging.INFO)

    sync_extension = os.path.splitext(args.sync)[1].lower()
    if sync_extension.lower() == '.srt':
        if not args.lang:
            logging.error('Missing --lang, provide the language of --input.')
            sys.exit(1)

        logging.info("Syncing input with subtitle...")
        input_track = open_subtitle(args.input)
        sync_track = open_subtitle(args.sync)

        if args.lang != 'en':
            translate_subtitle(sync_track, args.lang)
    elif sync_extension in VIDEO_EXTENSIONS:
        logging.info("Syncing input with movie...")
        input_track = open_subtitle(args.input)
        generated_subtitle = generate_subtitle(args.sync, args.output)
        sync_track = open_subtitle(generated_subtitle)

        if not args.debug:
            os.remove(generated_subtitle)
        else:
            logging.info('Autosub generated subtitle saved to %s.' %
                         generated_subtitle)
    else:
        logging.error(("Unable to detect sync method, -s/--sync is in "
                       "unsupported format."))
        sys.exit(1)

    matches = find_matches(input_track, sync_track)

    if len(matches) is 0:
        logging.error("Found no matches with sync input, unable to sync...")
        sys.exit(1)

    (coefficient, intercept) = calculate_linear_regression(matches)

    input_track = sync_with_linear_regression(input_track, coefficient,
                                              intercept)

    if args.debug:
        plot_matches(matches, '%s.html' % args.output, coefficient, intercept)

    # Remove subtitles that start and end on 00:00:00.0000.
    for s in input_track.slice(ends_before={'minutes': 0, 'seconds': 0}):
        del input_track[input_track.index(s)]

    # Renumber indexes
    for s in input_track:
        s.index = input_track.index(s)

    # Save subtitle.
    input_track.save(args.output, encoding='utf-8')

    logging.info("Done!")
