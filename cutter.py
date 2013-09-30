#!/usr/bin/env python

from cutter import formats, cue
from cutter.coding import to_unicode, to_bytes
from cutter.splitter import Splitter
from cutter.tools import *

from optparse import OptionParser, OptionGroup

import sys
import os

try:
	from cutter import config
except Exception as err:
	printerr("import config failed: %s", err)
	sys.exit(0)

def msf(ts):
	m = ts / (60 * 75)
	s = ts / 75 % 60
	f = ts % 75

	return "%d:%02d:%02d" % (m, s, f)

def print_cue(cue):
	for k, v in cue.attrs():
		printf("%s: %s\n", k.upper(), quote(v))

	for file in cue.files():
		name = cue.dir + file.name

		printf("FILE %s", quote(file.name))
		if not os.path.exists(name):
			printf(": not exists\n")
		else:
			info = StreamInfo.get(name)
			if not info:
				printf(": unknown type\n")
			else:
				printf(" [%s] (%d/%d, %d ch)\n",
					info.type,
					info.bits_per_sample,
					info.sample_rate,
					info.channels)

		for track in file.tracks():
			printf("\tTRACK %02d", track.number)
			title = track.get("title")
			if title != "":
				printf(" %s", quote(title))
			printf(": %s -", msf(track.begin))
			if track.end is not None:
				printf(" %s", msf(track.end))
			printf("\n")

			for k, v in track.attrs():
				if k not in ("pregap", "postgap", "title"):
					printf("\t\t%s: %s\n", k.upper(), quote(v))

def parse_args():
	parser = OptionParser(usage = u"Usage: %prog [options] cuefile")
	parser.add_option("--ignore",
		action="store_true", default=False, dest="ignore",
		help="ignore cue parsing errors")

	parser.add_option("--dump",
		dest="dump", choices=["cue", "tags", "tracks"],
		metavar="cue|tags|tracks",
		help="print the cue sheet, file tags or track names")

	parser.add_option("-n", "--dry-run",
		action="store_true", default=False, dest="dry_run")

	enc = OptionGroup(parser, "Encoding options")

	enc.add_option("-t", "--type", dest="type",
		choices = formats.supported() + ["help"],
		help="output file format")

	enc.add_option("--coding", dest="coding",
		help="encoding of original text")

	enc.add_option("-d", "--dir",
		dest="dir", default=config.DIR, help="output directory")

	enc.add_option("--use-tempdir",
		dest="use_tempdir", action="store_true",
		help="use temporary directory for files")

	enc.add_option("--no-tempdir",
		dest="use_tempdir", action="store_false",
		help="do not use temporary directory")

	enc.add_option("-C", "--compression", type="int",
		dest="compression", metavar="FACTOR",
		help="compression factor for output format (used for flac, ogg)")

	enc.add_option("--bitrate", type="int",
		dest="bitrate", default=config.MP3_BITRATE,
		help="audio bitrate (used for mp3)")

	parser.add_option_group(enc)

	fname = OptionGroup(parser, "Filename options")

	fname.add_option("--format",
		dest="fmt", default=config.FILENAME_FORMAT,
		help="the format string for new filenames")

	fname.add_option("--convert-chars",
		dest="convert_chars", action="store_true",
		help="replace illegal characters in filename")

	fname.add_option("--no-convert-chars",
		dest="convert_chars", action="store_false",
		help="do not replace characters in filename")

	parser.add_option_group(fname)

	format = OptionGroup(parser, "Output format")

	format.add_option("-r", "--sample-rate", type="int",
		dest="sample_rate", default=config.SAMPLE_RATE, metavar="RATE")

	format.add_option("-c", "--channels", type="int",
		dest="channels", default=config.CHANNELS)

	format.add_option("-b", "--bits-per-sample", type="int",
		dest="bits_per_sample", default=config.BITS_PER_SAMPLE, metavar="BITS")

	parser.add_option_group(format)

	tag = OptionGroup(parser, "Tag options")
	tag_options = ["album", "artist", ("date", "year"), "genre",
		"comment", "composer", "albumartist"]

	for opt in tag_options:
		if type(opt) in (list, tuple):
			tag.add_option(*["--" + s for s in opt], dest=opt[0], default="")
		else:
			tag.add_option("--" + opt, dest=opt, default="")

	parser.add_option_group(tag)

	return parser.parse_args()

def option_check_range(option, value, min, max):
	if value is not None and (value < min or value > max):
		printerr("invalid %s value %d, must be in range %d .. %d", option, value, min, max)
		return False

	return True

def process_options(opt):
	def choose(a, b):
		return a if a is not None else b

	if opt.type == "help":
		printerr("supported formats: " + " ".join(formats.supported()))
		return False

	if opt.type is None and config.TYPE:
		if not formats.issupported(config.TYPE):
			printerr("invalid configuration: type '%s' is not supported", config.TYPE)
			return False

		opt.type = config.TYPE

	if not opt.dump and opt.type is None:
		printerr("--type option is missed")
		return False

	if opt.type == "flac":
		opt.compression = choose(opt.compression, config.FLAC_COMPRESSION)
		if not option_check_range("compression", opt.compression, 0, 8):
			return False
	elif opt.type == "ogg":
		opt.compression = choose(opt.compression, config.OGG_COMPRESSION)
		if not option_check_range("compression", opt.compression, -1, 10):
			return False
	elif opt.type == "mp3":
		if not option_check_range("bitrate", opt.bitrate, 32, 320):
			return False

	if not opt.dir:
		opt.dir = u"."
	else:
		opt.dir = to_unicode(os.path.normpath(opt.dir))

	opt.fmt = to_unicode(opt.fmt)
	if not os.path.basename(opt.fmt):
		printerr("invalid format option \"%s\"", opt.fmt)
		return False
	else:
		opt.fmt = os.path.normpath(opt.fmt)
		if opt.fmt.startswith("/"):
			opt.fmt = opt.fmt[1:]

	if opt.convert_chars is None:
		opt.convert_chars = config.CONVERT_CHARS
	if opt.use_tempdir is None:
		opt.use_tempdir = config.USE_TEMPDIR

	return True

def find_cuefile(path):
	for file in os.listdir(path):
		fullname = os.path.join(path, file)
		if os.path.isfile(fullname) and file.endswith(".cue"):
			return fullname

	printerr("no cue file")
	sys.exit(1)

def main():
	options, args = parse_args()
	if not process_options(options):
		sys.exit(1)

	if len(args) != 1:
		printf("Usage: %s [options] cuefile\n", progname)
		return 1

	def on_error(err):
		printerr("%d: %s\n" % (err.line, err))
		if not options.ignore:
			raise StopIteration

	cuepath = to_unicode(args[0])
	if os.path.isdir(cuepath):
		cuepath = find_cuefile(cuepath)
		if options.dry_run:
			debug("use cue file %s", quote(cuepath))

	try:
		cuesheet = cue.read(cuepath, options.coding, on_error=on_error)
	except StopIteration:
		return 1
	except IOError as err:
		printerr("open %s: %s", err.filename, err.strerror)
		return 1
	except Exception as err:
		msg = "%s (%s)" % (err, err.__class__.__name__)

		if hasattr(err, "filename"):
			printerr("%s: %s: %s\n", err.filename, msg)
		else:
			printerr("%s\n", msg)

		return 1

	cuesheet.dir = os.path.dirname(cuepath)
	if cuesheet.dir:
		cuesheet.dir += "/"

	{
		"cue":		lambda: print_cue(cue),
		"tags":		lambda: Splitter(cuesheet, options).dump_tags(),
		"tracks":	lambda: Splitter(cuesheet, options).dump_tracks(),
		None:		lambda: Splitter(cuesheet, options).split()
	}[options.dump]()

	return 0

if __name__ == '__main__':
	sys.exit(main())