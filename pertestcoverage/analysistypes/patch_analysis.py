import os
import time
import logging

from ..cli import AnalysisParser

from ..utils.cocoload import (
	save_json,
	get_http_json,
	query_activedata
)

HG_URL = "https://hg.mozilla.org/"

log = logging.getLogger('pertestcoverage')


def run(args):
	"""
		Expects a `config` with the following settings:

			numpatches: 100
			startrev: "48cc597db296"
			outputdir: "C:/tmp/"
			analysisbranch: "mozilla-central"

			mochitest_tc_task_rev: "dcb3a3ba9065"
			mochitest_tc_task_branch: "try"
			xpcshell_tc_task_rev: "6369d1c6526b"
			xpcshell_tc_task_branch: "try" 

			analyze_files_with_missing_tests: True
	"""
	parser = AnalysisParser('config')
	args = parser.parse_analysis_args(args)

	numpatches = args.config['numpatches']
	startrevision = args.config['startrev']
	analysisbranch = args.config['analysisbranch']
	outputdir = args.config['outputdir']
	analyze_files_with_missing_tests = args.config['analyze_files_with_missing_tests']

	# JSON to use for test file queries
	mochitest_query_json = {
		"from":"coverage",
		"where":{
			"and":[
				{"eq":{"source.file.name":None}},
				{"eq":{"repo.changeset.id12":args.config['mochitest_tc_task_rev']}},
				{"eq":{"repo.branch.name":args.config['mochitest_tc_task_branch']}},
				{"gt":{"source.file.total_covered":0}}
			]
		},
		"limit":1000,
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
				{"eq":{"repo.changeset.id12":args.config['xpcshell_tc_task_rev']}},
				{"eq":{"repo.branch.name":args.config['xpcshell_tc_task_branch']}},
				{"gt":{"source.file.total_covered":0}}
			]
		},
		"limit":1000,
		"select":[
			{"name":"test","value":"test.name"},
			{"name":"coverage","value":"source.file.covered"}
		]
	}

	# Get all patches
	changesets = []
	keep_going = True
	currrev = startrevision

	while len(changesets) < numpatches:
		changelog_url = HG_URL + analysisbranch + "/json-log/" + currrev

		data = get_http_json(changelog_url)
		clog_csets_list = list(data['changesets'])
		changesets.extend([el['node'][:12] for el in clog_csets_list[:-1]])

		currrev = clog_csets_list[-1]['node'][:12]

	changesets = changesets[:numpatches]

	tests_for_changeset = {}
	tests_per_file = {}

	# For each patch
	for changeset in changesets:
		log.info("On changeset: " + changeset)

		# Get patch
		files_url = HG_URL + analysisbranch + "/json-info/" + changeset
		data = get_http_json(files_url)

		files_modified = data[changeset]['files']

		# Get tests that use this patch
		all_tests = set()

		if not analyze_files_with_missing_tests:
			for file in files_modified:
				mochitest_query_json['where']['and'][0]['eq']['source.file.name'] = file
				xpcshell_query_json['where']['and'][0]['eq']['source.file.name'] = file

				mochi_tests = query_activedata(mochitest_query_json)
				xpc_tests = query_activedata(xpcshell_query_json)

				if 'test' not in mochi_tests:
					mochi_tests['test'] = []
				if 'test' not in xpc_tests:
					xpc_tests['test'] = []

				tests_per_file[file] = list(set(mochi_tests['test']) | set(xpc_tests['test']))
				all_tests = list(set(all_tests) | (set(mochi_tests['test']) | set(xpc_tests['test'])))
		else:
			in_entry = {"in": {"source.file.name": files_modified}}
			groupby_entry = [{"name":"test","value":"test.name"}]

			if 'select' in mochitest_query_json:
				del mochitest_query_json['select']
			if 'select' in xpcshell_query_json:
				del xpcshell_query_json['select']

			mochitest_query_json['groupby'] = groupby_entry
			xpcshell_query_json['groupby'] = groupby_entry
			mochitest_query_json['where']['and'][0] = in_entry
			xpcshell_query_json['where']['and'][0] = in_entry

			mochi_tests = [testchunk[0] for testchunk in query_activedata(mochitest_query_json)]
			xpc_tests = [testchunk[0] for testchunk in query_activedata(xpcshell_query_json)]

			all_tests = list(set(mochi_tests) | set(xpc_tests))

		log.info("Number of tests: " + str(len(all_tests)))
		log.info("Number of files: " + str(len(files_modified)))
		log.info("Files with no tests: " + str([file for file in tests_per_file if file in files_modified and not tests_per_file[file]]))
		log.info("\n")

		tests_for_changeset[changeset] = {}
		tests_for_changeset[changeset]['patch-link'] = HG_URL + analysisbranch + "/rev/" + changeset
		tests_for_changeset[changeset]['numfiles'] = len(files_modified)
		tests_for_changeset[changeset]['numtests'] = len(all_tests)
		tests_for_changeset[changeset]['tests'] = all_tests

	# Save result (number, and all tests scheduled)
	files_with_no_tests = {
		"files": [file for file in tests_per_file if file in files_modified and not tests_per_file[file]]
	}

	log.info("\nSaving results to output directory: " + outputdir)
	save_json(tests_for_changeset, outputdir, str(int(time.time())) + '_tests_scheduled_per_changeset.json')

	if not analyze_files_with_missing_tests:
		save_json(tests_per_file, outputdir, str(int(time.time())) + '_tests_scheduled_per_file.json')
		save_json(files_with_no_tests, outputdir, str(int(time.time())) + '_files_with_no_tests.json')
