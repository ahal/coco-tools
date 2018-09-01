import os
import argparse
from utils.cocoload import (
	get_per_test_scored_file,
	get_per_test_file,
	pattern_find,
	open_json,
	save_json
)


def parse_json2url_args():
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"PER_TEST_DIR", nargs='+', type=str,
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
	return parser


def main():
	# Finds tests and shows the coverage for each of it's files.
	args = parse_json2url_args().parse_args()

	places_to_search = args.PER_TEST_DIR
	url_prefix = 'https://hg.mozilla.org/'
	revision = args.revision
	branch = args.branch
	sources = args.sources
	differences = args.differences
	find_files = []

	if differences:
		print("Converting differences JSONs.")
		for data_dir in places_to_search:
			if os.path.isfile(data_dir):
				root, file = os.path.split(data_dir)
				data_dir = root
				find_files.append(file)

			for root, _, files in os.walk(data_dir):
				for file in files:
					if '.json' not in file:
						continue
					if file not in find_files:
						continue

					new_fname = os.path.splitext(file)[0] + '_urls.json'
					try:
						json_data = open_json(root, file)
						new_entry = {}
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
										url_prefix +
										branch + "/" +
										'annotate'  + "/" +
										revision + "/" +
										fname.lstrip('/') +
										"#l" + str(line)
										for line in lines
									]
							new_entry[entry] = new_fchunk
						save_json(new_entry, root, new_fname)
					except Exception as e:
						print("Bad JSON found: " + str(os.path.join(root,file)))
						continue
					print("Converted: " + file)
					print("To: " + new_fname)
					print("\n")
	else:
		print("Must supply the type of JSON to convert, i.e. --differences")

if __name__ == "__main__":
	main()