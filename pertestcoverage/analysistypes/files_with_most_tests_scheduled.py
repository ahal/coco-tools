import os
import time
import logging
import numpy as np
from matplotlib import pyplot as plt

from ..cli import AnalysisParser

from ..utils.cocoload import (
	save_json,
	get_http_json,
	query_activedata,
	get_changesets,
	HG_URL
)

log = logging.getLogger('pertestcoverage')


def run(args=None, config=None):
	"""
		Expects a `config` with the following settings:

			numpatches: 100
			startrev: "48cc597db296"
			outputdir: "C:/tmp/"
			analysisbranch: "mozilla-central"
			hg_analysisbranch: "mozilla-central"
			minimum_tests: 1
			num_test_counts_in_worst_case: 8000

			Optional(
				changesets: ["125hV21eE49", ...]
			)

			mochitest_tc_task_rev: "dcb3a3ba9065"
			mochitest_tc_task_branch: "try"
			xpcshell_tc_task_rev: "6369d1c6526b"
			xpcshell_tc_task_branch: "try" 
	"""
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")

	numpatches = config['numpatches']
	startrevision = config['startrev']
	analysisbranch = config['analysisbranch']
	hg_analysisbranch = config['hg_analysisbranch']
	minimum_tests = config['minimum_tests']
	num_test_counts_in_worst_case = config['num_test_counts_in_worst_case']
	changesets = [] if 'changesets' not in config else config['changesets']

	outputdir = config['outputdir']

	# JSON to use for test file queries
	mochitest_query_json = {
		"from":"coverage",
		"where":{
			"and":[
				{"eq":{"source.file.name":None}},
				{"eq":{"repo.changeset.id12":config['mochitest_tc_task_rev']}},
				{"eq":{"repo.branch.name":config['mochitest_tc_task_branch']}},
				{"gt":{"source.file.total_covered":0}}
			]
		},
		"limit":100000,
		"select":[
			{"name":"test","value":"test.name"},
			{"name":"coverage","value":"source.file.covered"}
		]
	}

	xpcshell_query_json = {
		"from":"coverage",
		"where":{
			"and":[
				{"eq":{"source.file.name":None}},
				{"eq":{"repo.changeset.id12":config['xpcshell_tc_task_rev']}},
				{"eq":{"repo.branch.name":config['xpcshell_tc_task_branch']}},
				{"gt":{"source.file.total_covered":0}}
			]
		},
		"limit":100000,
		"select":[
			{"name":"test","value":"test.name"},
			{"name":"coverage","value":"source.file.covered"}
		]
	}

	mochitest_all_query_json = {
		"from":"coverage",
		"where":{
			"and":[
				{"in": {"source.file.name": []}},
				{"eq":{"repo.changeset.id12":config['mochitest_tc_task_rev']}},
				{"eq":{"repo.branch.name":config['mochitest_tc_task_branch']}},
				{"gt":{"source.file.total_covered":0}}
			]
		},
		"limit":100000,
		"groupby": [{"name":"test","value":"test.name"}]
	}

	xpcshell_all_query_json = {
		"from":"coverage",
		"where":{
			"and":[
				{"in": {"source.file.name": []}},
				{"eq":{"repo.changeset.id12":config['xpcshell_tc_task_rev']}},
				{"eq":{"repo.branch.name":config['xpcshell_tc_task_branch']}},
				{"gt":{"source.file.total_covered":0}}
			]
		},
		"limit":100000,
		"groupby": [{"name":"test","value":"test.name"}]
	}

	# Get number of patches requested
	if not changesets:
		changesets = get_changesets(hg_analysisbranch, startrevision, numpatches)

	per_changeset_info = {}
	tests_per_file = {}

	# For each patch
	for count, changeset in enumerate(changesets):
		log.info("On changeset " + "(" + str(count+1) + "): " + changeset)

		# Get patch
		files_url = HG_URL + hg_analysisbranch + "/json-info/" + changeset
		data = get_http_json(files_url)

		files_modified = data[changeset]['files']

		if not files_modified:
			continue

		if num_test_counts_in_worst_case > 0:
			in_entry = {"in": {"source.file.name": files_modified}}
			mochitest_all_query_json['where']['and'][0] = in_entry
			xpcshell_all_query_json['where']['and'][0] = in_entry

			try:
				mochi_tests = [testchunk[0] for testchunk in query_activedata(mochitest_all_query_json)]
				xpc_tests = [testchunk[0] for testchunk in query_activedata(xpcshell_all_query_json)]
			except Exception as e:
				log.info("Error running query: " + str(mochitest_query_json))
				log.info("or the query: " + str(xpcshell_query_json))
				continue

			# No tests scheduled
			if (len(mochi_tests) == 0 and len(xpc_tests) == 0):
				log.info("No tests scheduled.")
				continue

			tmp_tests = list(set(mochi_tests) | set(xpc_tests))
			if len(tmp_tests) < num_test_counts_in_worst_case:
				log.info("Not enough tests scheduled: " + str(len(tmp_tests)) + " < " + str(num_test_counts_in_worst_case))
				continue
			log.info("Found " + str(len(tmp_tests)) + " tests to run.")

		# Get tests that use this patch
		all_tests = []
		for file in files_modified:
			if file in tests_per_file:
				all_tests.extend(tests_per_file[file])
				continue

			mochitest_query_json['where']['and'][0]['eq']['source.file.name'] = file
			xpcshell_query_json['where']['and'][0]['eq']['source.file.name'] = file

			try:
				mochi_tests = query_activedata(mochitest_query_json)
				xpc_tests = query_activedata(xpcshell_query_json)
			except Exception as e:
				log.info("Error running with file: " + file)

			if 'test' not in mochi_tests:
				mochi_tests['test'] = []
			if 'test' not in xpc_tests:
				xpc_tests['test'] = []

			tests_per_file[file] = list(set(mochi_tests['test']) | set(xpc_tests['test']))
			all_tests = list(set(all_tests) | (set(mochi_tests['test']) | set(xpc_tests['test'])))

		log.info("Number of tests: " + str(len(all_tests)))
		log.info("Number of files: " + str(len(files_modified)))
		log.info("Files with no tests: " + str([file for file in tests_per_file if file in files_modified and not tests_per_file[file]]))
		log.info("\n")

		per_changeset_info[changeset] = {}
		per_changeset_info[changeset]['files'] = files_modified
		per_changeset_info[changeset]['total_tests'] = len(tmp_tests)
		per_changeset_info[changeset]['numtests_per_file'] = {
			file: len(tests_per_file[file])
			for file in files_modified
		}

	tests_per_file = {file: tests for file, tests in tests_per_file.items() if len(tests) >= minimum_tests}
	tests_count_per_file = {file: len(tests) for file, tests in tests_per_file.items()}

	if outputdir:
		log.info("\nSaving results to output directory: " + outputdir)
		save_json(tests_per_file, outputdir, str(int(time.time())) + '_tests_scheduled_per_file.json')
		save_json(tests_count_per_file, outputdir, str(int(time.time())) + '_count_of_tests_scheduled_per_file.json')
		save_json(per_changeset_info, outputdir, str(int(time.time())) + '_per_changeset_info.json')
	else:
		log.info(str(tests_per_file))
		log.info(str(tests_count_per_file))
