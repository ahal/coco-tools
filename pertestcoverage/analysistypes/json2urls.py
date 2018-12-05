import os
import argparse

from ..cli import AnalysisParser
from ..utils.cocoload import (
	get_per_test_scored_file,
	get_per_test_file,
	pattern_find,
	open_json,
	save_json
)

URL_PREFIX = 'https://hg.mozilla.org/'

def parse_json2url_args():
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"json_locations_list", nargs='+', type=str,
		help="Directory containing json's created by pertestcoverage_variability. Must contain only " +
			 "JSON reports (or many folders of them)."
	)
	parser.add_argument(
		"-r", "--revision", type=str, required=True,
		help='Revision to use on the specified branch in the hg annotate URL.'
	)
	parser.add_argument(
		"-b", "--branch", type=str, default='mozilla-central',
		help='Branch to find file on.'
	)
	parser.add_argument(
		"-s", "--sources", nargs='+', default=None,
		help='Source files to find, these are pattern matchers.'
	)
	parser.add_argument(
		"--differences", action="store_true", default=False,
		help='Source files to find, these are pattern matchers.'
	)
	parser.add_argument(
		"--pertestcoverage-view", action="store_true", default=False,
		help='Source files to find, these are pattern matchers.'
	)
	return parser


def file_to_hgloc(fname, line, branch, revision):
	return \
		URL_PREFIX + \
		branch + "/" + \
		'file'  + "/" + \
		revision + "/" + \
		fname.lstrip('/') + \
		"#l" + str(line)


def json2url(
		json_data,
		revision,
		branch='mozilla-central',
		sources=None
	):
	new_entry = {}

	if differences:
		for entry in json_data:
			if 'location' in entry:
				continue

			new_fchunk = {}
			for fname, diffs in json_data[entry].items():
				new_fchunk[fname] = {}
				for diff, lines in diffs.items():
					if sources and not pattern_find(fname, sources):
						continue
					new_fchunk[fname][diff] = [
						file_to_hgloc(fname, line, branch, revision)
						for line in lines
					]
			new_entry[entry] = new_fchunk

	elif pertestcoverage_view:
		for fname, lines in json_data.items():
			if sources and not pattern_find(fname, sources):
				continue

			new_entry[fname] = [
				file_to_hgloc(fname, line, branch, revision)
				for line in lines
			]

	return new_entry


def json2urls(
		json_locations_list,
		revision,
		branch='mozilla-central',
		sources=None,
		differences=False,
		pertestcoverage_view=False
	):
	# Finds jsons and converts their coverage
	# contents into hg urls.
	find_files = []

	if not differences and not pertestcoverage_view:
		print("Must supply the type of JSON to convert, i.e. --differences")
		return

	for data_dir in json_locations_list:
		is_file = os.path.isfile(data_dir)
		if is_file:
			root, file = os.path.split(data_dir)
			data_dir = root
			find_files.append(file)

		for root, _, files in os.walk(data_dir):
			for file in files:
				if '.json' not in file:
					continue
				if is_file and file not in find_files:
					continue

				new_fname = os.path.splitext(file)[0] + '_urls.json'
				try:
					json_data = open_json(root, file)

					if pertestcoverage_view:
						if not file.startswith('view') or \
						   '_urls' in file and file.startswith('view'):
							continue

					new_entry = json2url(
						json_data,
						revision,
						branch=branch,
						sources=sources
					)

					save_json(new_entry, root, new_fname)
				except Exception as e:
					print("Bad JSON found: " + str(os.path.join(root,file)) + "\n\nCause:\n" + str(e))
					continue
				print("Converted: " + file)
				print("To: " + new_fname)
				print("\n")

	print("Finished conversion.")



def run(args):
	"""
		Expects `config` to at least contain:

			json_locations_list: C:/Users/gm/Documents/per-test-coverage-data/
			sources:
				- test
				- .cpp
			differences: True

		`differences` can be replaced with `pertestcoverage_view` if that's the style of json being given.
	"""
	parser = AnalysisParser('config', 'branch', 'rev')
	args = parser.parse_analysis_args(args)
	json2urls(
		args.config['json_locations_list'],
		args.rev,
		**args.config
	)


if __name__ == "__main__":
	args = parse_json2url_args().parse_args()
	pertestcoverage_json2urls(
		args.json_locations_list,
		args.revision,
		branch = args.branch,
		sources = args.sources,
		differences = args.differences,
		pertestcoverage_view = args.pertestcoverage_view
	)
