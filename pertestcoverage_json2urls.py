import os
import argparse
from utils.cocoload import (
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
		"PLACES_TO_SEARCH", nargs='+', type=str,
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


def file_to_annotate(fname, line, branch, revision):
	return \
		URL_PREFIX + \
		branch + "/" + \
		'annotate'  + "/" + \
		revision + "/" + \
		fname.lstrip('/') + \
		"#l" + str(line)


def main():
	# Finds tests and shows the coverage for each of it's files.
	args = parse_json2url_args().parse_args()

	places_to_search = args.PLACES_TO_SEARCH
	revision = args.revision
	branch = args.branch
	sources = args.sources
	differences = args.differences
	pertestcoverage_view = args.pertestcoverage_view
	find_files = []

	if not differences and not pertestcoverage_view:
		print("Must supply the type of JSON to convert, i.e. --differences")
		return

	print("Converting differences JSONs.")
	for data_dir in places_to_search:
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
										file_to_annotate(fname, line, branch, revision)
										for line in lines
									]
							new_entry[entry] = new_fchunk
					elif pertestcoverage_view:
						if not file.startswith('view') or \
						   '_urls' in file and file.startswith('view'):
							continue

						for fname, lines in json_data.items():
							if sources and not pattern_find(fname, sources):
								continue
							new_entry[fname] = [
								file_to_annotate(fname, line, branch, revision)
								for line in lines
							]

					save_json(new_entry, root, new_fname)
				except Exception as e:
					print("Bad JSON found: " + str(os.path.join(root,file)) + "\n\nCause:\n" + str(e))
					continue
				print("Converted: " + file)
				print("To: " + new_fname)
				print("\n")


if __name__ == "__main__":
	main()