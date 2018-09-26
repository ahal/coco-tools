import os
import argparse
import time

from ..cli import AnalysisParser
from utils.cocoload import (
	get_per_test_scored_file,
	get_per_test_file,
	pattern_find,
	save_json
)


def parse_view_args():
	parser = argparse.ArgumentParser()
	parser.add_argument(
		"per_test_dir", type=str,
		help="Directory containing per-test-coverage-reports. Must contain only " +
			 "JSON reports (or many folders of them)."
	)
	parser.add_argument(
		"-t", "--tests", nargs='+', required=True,
		help='Tests to look at.'
	)
	parser.add_argument(
		"-s", "--sources", nargs='+', default=None,
		help='Source files to find, these are pattern matchers.'
	)
	parser.add_argument(
		"--scores", nargs='+', type=float,
		help='[low, high] (inclusive): For looking at files with a score. ' +
			 'Ignored when --scoredfile is not used.'
	)
	parser.add_argument(
		"--getuniques", action="store_false", default=True,
		help='Returns unique lines for the test when a score range is given. (As a score of None indicates a unique test line). ' +
			 'Ignored when --scoredfile is not used.'
	)
	parser.add_argument(
		"--scoredfile", action="store_true", default=False,
		help='Set this flag if a file with the percent-change score is being looked at.'
	)
	parser.add_argument(
		"--save-view-json", type=str, default=None,
		help='If set, a JSON with the parsed coverage will be saved (for use in pertestcoverage_json2urls.py with --view).'
	)
	return parser


def view_file(
		root=None,
		file=None,
		full_path=None,
		score_range=None,
		ignore_uniques=True
	):
	if not (root and file and full_path):
		raise Exception("No file paths supplied.")
	if not full_path and root or file and not (file and root):
		raise Exception("root and file must both me supplied if full_path is not.")

	if full_path:
		root, file = os.path.split(full_path)

	if scored_file:
		fmtd_test_dict = get_per_test_scored_file(
			root, file, return_test_name=True,
			score_range=score_range, ignore_uniques=ignore_uniques
		)
	else:
		fmtd_test_dict = get_per_test_file(
			root, file, return_test_name=True
		)

	return fmtd_test_dict


def view(
		per_test_dir,
		test_files,
		score_range=None,
		scored_file=False,
		sources=None,
		ignore_uniques=True,
		save_view_json=''
	):

	# Finds tests and shows the coverage for each of it's files.

	for root, _, files in os.walk(DATA_DIR):
		for file in files:
			if '.json' not in file:
				continue

			try:
				fmtd_test_dict = view_file(
					root=root,
					file=file,
					score_range=score_range,
					scored_file=scored_file,
					ignore_uniques=ignore_uniques
				)
			except KeyError as e:
				print("Bad JSON found: " + str(os.path.join(root,file)))
				continue


			print("--With root: " + root)
			print("--From file: " + file)

			test_name = fmtd_test_dict['test']
			suite_name = fmtd_test_dict['suite']
			if not pattern_find(test_name, args.tests):
				continue

			filt_test_dict = {
				sf: fmtd_test_dict['source_files'][sf]
				for sf in fmtd_test_dict['source_files']
				if pattern_find(sf, sources)
			}

			print("Test-name: " + test_name)
			print("Suite: " + suite_name)
			print(
				"Coverage: \n" + "\n\n".join(
					[
						str(sf) + ": " +
						str(filt_test_dict[sf]) for sf in filt_test_dict
					]
				)
			)
			print("\n")

			if save_view_json:
				save_json(
					filt_test_dict,
					save_view_json,
					'view_' + os.path.splitext(file)[0] + '_' + str(int(time.time())) + '.json'
				)


def run(args):
	parser = AnalysisParser('config')
	args = parser.parse_analysis_args(args)
	view(
		args.config['pertestdir'],
		**args.config
	)


if __name__ == "__main__":
	args = parse_view_args().parse_args()
	view(
		args.per_test_dir,
		test_files = args.tests,
		score_range = args.scores,
		scored_file = args.scoredfile,
		sources = args.sources,
		ignore_uniques = args.getuniques,
		save_view_json = args.save_view_json
	)