import os

from ..cli import AnalysisParser

from ..utils.cocoload import (
	get_http_json,
	query_activedata
)

HG_URL = "https://hg.mozilla.org/"


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

	"""
	parser = AnalysisParser('config')
	args = parser.parse_analysis_args(args)

	numpatches = args.config['numpatches']
	startrevision = args.config['startrev']
	analysisbranch = args.config['analysisbranch']
	outputdir = args.config['outputdir']

	# JSON to use for test file queries
	mochitest_query_json = {
		"from":"coverage",
		"where":{
			"and":[
				{"eq":{"source.file.name":None}},
				{"eq":{"repo.changeset.id12":args.config['mochitest_tc_task_rev']}},
				{"eq":{"repo.branch.name":args.config['mochitest_tc_task_branch']}}
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
				{"eq":{"repo.branch.name":args.config['xpcshell_tc_task_branch']}}
			]
		},
		"limit":1000,
		"select":[
			{"name":"test","value":"test.name"},
			{"name":"coverage","value":"source.file.covered"}
		]
	}

	# Get all patches
	changesets = [startrevision]
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
		print("On changeset: " + changeset)

		# Get patch
		files_url = HG_URL + analysisbranch + "/json-info/" + changeset
		data = get_http_json(files_url)

		files_modified = data[changeset]['files']

		# Get tests that use this patch
		all_tests = set()
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

		tests_for_changeset[changeset] = {}
		tests_for_changeset[changeset]['numtests'] = len(all_tests)
		tests_for_changeset[changeset]['tests'] = all_tests

	# Save result (number, and all tests scheduled)
	print(tests_for_changeset)
