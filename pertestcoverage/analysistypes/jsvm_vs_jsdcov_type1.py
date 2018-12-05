import os
import json
import copy
import logging

from ..cli import AnalysisParser

from ..utils.cocoload import (
	save_json,
	chrome_mapping_rewrite,
	query_activedata
)
from ..utils.cocoanalyze.general_comparison import (
	compare_coverage_files
)

RETRY = {"times": 3, "sleep": 5}

log = logging.getLogger("pertestcoverage")


def get_sets_common_and_different(files1, files2, forward_diff_name='list1-list2',
								 backward_diff_name='list2-list1', merge_diffs=False):
	different = {}
	common = list(files1 & files2)

	if not merge_diffs:
		different[forward_diff_name] = list(files1-files2)
		different[backward_diff_name] = list(files2-files1)
	else:
		different = list(files1 ^ files2)

	return (common, different)


def correct_ccov_for_baseline(ccov_data, baseline_ccov_data, level='file'):
	# Expects data strucutres like what is returned by jsonify_ccov_artifact(...).

	# Get level differences and common
	# The forward diff (ccov_data-baseline_ccov_data) is
	# what we are after.
	file1_name = 'ccov'
	file2_name = 'base'
	forward_diff_name = file1_name + '-' + file2_name
	_, different = compare_coverage_files(
		ccov_data, baseline_ccov_data, level=level,
		file1_name=file1_name, file2_name=file2_name
	)

	unique_to_data = {}
	if level == "file":
		unique_to_data = different[forward_diff_name]
	else:
		# Return to standard form
		for srcFile in different: # For each source file
			unique_to_data[srcFile] = different[srcFile][forward_diff_name]
	return unique_to_data


def get_common_and_different(fmt_coverage1, fmt_coverage2, cov1_fname='jsdcov', cov2_fname='jsvm',
							 merge_line_diffs=False, level='file'):
	common_to_both = {}
	different_between = {}
	for count1, artifact1 in enumerate(fmt_coverage1):
		for count2, artifact2 in enumerate(fmt_coverage2):
			common, different = compare_coverage_files(
				artifact1, artifact2,
				level=level, file1_name=cov1_fname,
				file2_name=cov2_fname, merge_line_diffs=merge_line_diffs
			)

			curr_name = str(count1) + '-' + str(count2)
			common_to_both[curr_name] = common
			different_between[curr_name] = different

	return common_to_both, different_between


def run(args=None, config=None):
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")

	# Analysis 1, check similarities and differences. (No aggregation)
	level = config['level']
	merge_line_diffs = config['merge_line_diffs']
	outputdir = config['outputdir']

	jsvm_taskid = config['jsvm_taskid']
	jsvm_baseline_taskid = config['jsvm_baseline_taskid']
	jsdcov_taskid = config['jsdcov_taskid']
	jsdcov_baseline_taskid = config['jsdcov_baseline_taskid']

	coverage_query_json = {
		"from": "coverage",
		"where": {
			"and": [
				{"eq": {"task.id": None}},
				{"gt": {"source.file.total_covered": 0}}
			]
		},
		"limit": 10000,
		"select": [
			{"name": "file", "value": "source.file.name"},
			{"name": "coverage", "value": "source.file.covered"}
		]
	}

	def format_results(data):
		if 'file' not in data or 'coverage' not in data:
			return {}

		tmp = zip(data['file'], data['coverage'])
		res = {}
		for file, coverage in tmp:
			res[file] = coverage
		return res

	log.info("Gathering data...")

	# Get JSVM data
	coverage_query_json['where']['and'][0]['eq']['task.id'] = jsvm_taskid
	jsvm_data = format_results(query_activedata(coverage_query_json))

	coverage_query_json['where']['and'][0]['eq']['task.id'] = jsvm_baseline_taskid
	jsvm_baseline_data = format_results(query_activedata(coverage_query_json))

	# Get JSDCOV data
	coverage_query_json['where']['and'][0]['eq']['task.id'] = jsdcov_taskid
	jsdcov_data = format_results(query_activedata(coverage_query_json))

	coverage_query_json['where']['and'][0]['eq']['task.id'] = jsdcov_baseline_taskid
	jsdcov_baseline_data = format_results(query_activedata(coverage_query_json))

	jsvm_basecorr_data = jsvm_data #correct_ccov_for_baseline(jsvm_data, jsvm_baseline_data)
	jsdcov_basecorr_data = correct_ccov_for_baseline(jsdcov_data, jsdcov_baseline_data)

	save_json(jsdcov_data, outputdir, 'jsdcov_saveit.json')
	save_json(jsvm_data, outputdir, 'jsvm_saveit.json')
	save_json(jsdcov_basecorr_data, outputdir, 'jsdcov-base.json')
	save_json(jsvm_basecorr_data, outputdir, 'jsvm-base.json')

	log.info("Getting differences...")
	common_to_both = {}
	different_between = {}
	common_to_both, different_between = get_common_and_different(
		[jsdcov_basecorr_data], [jsvm_basecorr_data],
		cov1_fname='jsdcov', cov2_fname='jsvm', level=level,
		merge_line_diffs=merge_line_diffs
	)

	# Save before proceeding
	log.info("Saving results to: " + str(outputdir))
	filen = 'common.json'
	with open(os.path.join(outputdir, filen), 'w+') as f:
		json.dump(common_to_both, f, indent=4)

	filen = 'differences.json'
	with open(os.path.join(outputdir, filen), 'w+') as f:
		json.dump(different_between, f, indent=4)
