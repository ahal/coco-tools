import os
import argparse
import time
import logging

from ..cli import AnalysisParser
from ..utils.cocoload import (
	chrome_mapping_rewrite,
	file_in_type,
	get_and_check_config,
	get_per_test_scored_file,
	get_per_test_file,
	get_jsvm_file,
	get_jsdcov_file,
	get_std_ptc_file,
	pattern_find,
	save_json,
	TYPE_PERTEST,
	TYPE_LCOV,
	TYPE_JSDCOV,
	TYPE_STDPTC
)

log = logging.getLogger('pertestcoverage')


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
		filetype="pertestreport",
		full_path=None,
		score_range=None,
		scored_file=False,
		ignore_uniques=True,
		chrome_map=None # Required for 'lcov' filetype
	):
	if not (root and file) and not full_path:
		raise Exception("No file paths supplied.")
	if not full_path and ((root and not file) or (file and not root)):
		raise Exception("root and file must both me supplied if full_path is not.")

	if full_path:
		root, file = os.path.split(full_path)

	fmtd_test_dict = {}
	if filetype == TYPE_PERTEST:
		if scored_file:
			fmtd_test_dict = get_per_test_scored_file(
				root, file, return_test_name=True,
				score_range=score_range, ignore_uniques=ignore_uniques
			)
		else:
			fmtd_test_dict = get_per_test_file(
				root, file, return_test_name=True
			)
	elif filetype == TYPE_LCOV:
		chrome_map_path, chrome_map_name = os.path.split(chrome_map)
		fmtd_test_dict = chrome_mapping_rewrite(
			get_jsvm_file(root, file),
			chrome_map_path, chrome_map_name
		)
	elif filetype == TYPE_JSDCOV:
		chrome_map_path, chrome_map_name = os.path.split(chrome_map)
		fmtd_test_dict = chrome_mapping_rewrite(
			get_jsdcov_file(root, file, get_test_url=True),
			chrome_map_path, chrome_map_name
		)
	elif filetype == TYPE_STDPTC:
		chrome_map_path, chrome_map_name = os.path.split(chrome_map)
		fmtd_test_dict = chrome_mapping_rewrite(
			get_std_ptc_file(root, file),
			chrome_map_path, chrome_map_name
		)
	return fmtd_test_dict


def view(
		per_test_dir,
		test_files,
		filetype,
		score_range=None,
		scored_file=False,
		sources=None,
		ignore_uniques=True,
		chrome_map=None,
		outputdir='',
		delay=0,
		show_total=True,
		show_src_coverage=True
	):

	# Finds tests and shows the coverage for each of it's files.
	total_datapoints = 0
	found_test = False
	tests_found = []
	for root, _, files in os.walk(per_test_dir):
		for file in files:
			if not file_in_type(file, filetype):
				continue
			try:
				fmtd_test_dict = view_file(
					root=root,
					file=file,
					filetype=filetype,
					score_range=score_range,
					scored_file=scored_file,
					ignore_uniques=ignore_uniques,
					chrome_map=chrome_map
				)
			except Exception as e:
				log.info("Bad JSON found: " + str(os.path.join(root,file)))
				log.info("Exception: %s" % str(e))
				continue

			total_datapoints += 1

			test_name = ''
			suite_name = ''
			if 'test' in fmtd_test_dict:
				test_name = fmtd_test_dict['test']
			if 'suite' in fmtd_test_dict:
				suite_name = fmtd_test_dict['suite']
			if 'source_files' not in fmtd_test_dict:
				fmtd_test_dict = {
					'source_files': fmtd_test_dict.copy()
				}

			if test_name:
				if not pattern_find(test_name, test_files):
					continue
				tests_found.append(test_name)
			else:
				log.info("No test names found in data, showing all tests.")

			found_test = True

			filt_test_dict = {
				sf: fmtd_test_dict['source_files'][sf]
				for sf in fmtd_test_dict['source_files']
				if pattern_find(sf, sources)
			}

			log.info("--With root: " + root)
			log.info("--From file: " + file)
			log.info("Test-name: " + test_name)
			log.info("Suite: " + suite_name)

			if not filt_test_dict:
				log.info("Found no source files.")
				continue

			if show_src_coverage:
				log.info(
					"Coverage: \n" + "\n\n".join(
						[
							str(sf) + ": " +
							str(filt_test_dict[sf]) for sf in filt_test_dict
						]
					)
				)
			else:
				log.info("Found coverage for requested files.")

			log.info("")

			if delay:
				time.sleep(delay)

			if outputdir:
				save_json(
					filt_test_dict,
					outputdir,
					'view_' + os.path.splitext(file)[0] + '_' + str(int(time.time())) + '.json'
				)

	if not found_test:
		log.info("Found data, but not the requested tests.")
	else:
		tests_not_found = []
		for testf in test_files:
			found = False
			for test in tests_found:
				if testf in test:
					found = True
					break
			if not found:
				tests_not_found.append(testf)
		log.info("Could not find data for these tests: " + str(tests_not_found))

	if show_total:
		log.info("Total number of data points observed: " + str(total_datapoints))


def run(args=None, config=None):
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")

	view(
		**config
	)


if __name__ == "__main__":
	args = parse_view_args().parse_args()
	view(
		args.per_test_dir,
		test_files=args.tests,
		filetype="pertestreport",
		score_range=args.scores,
		scored_file=args.scoredfile,
		sources=args.sources,
		ignore_uniques=args.getuniques,
		save_view_json=args.save_view_json
	)