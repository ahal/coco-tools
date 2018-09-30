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


def plot_histogram(data, x_labels, title, figure=None, **kwargs):
	if not figure:
		f = plt.figure()
	else:
		plt.figure(f.number)

	x = range(len(data))

	b = plt.bar(x, data, **kwargs)
	plt.xticks(x, x_labels, rotation='vertical')
	plt.title(title)

	return f, b


def run(args=None, config=None):
	"""
		Expects a `config` with the following settings:

			numpatches: 100
			startrev: "48cc597db296"
			outputdir: "C:/tmp/"
			analysisbranch: "mozilla-central"
			hg_analysisbranch: "mozilla-central"
			platform_prefix: "test-"
			seta_suites: ["mochitest", "xpcshell"]

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
	platform_prefix = config['platform_prefix']
	seta_suites = config['seta_suites']
	changesets = [] if 'changesets' not in config else config['changesets']
	outputdir = config['outputdir']

	exclude_failed_tests = [
		"Main app process exited normally",
		"Last test finished"
	]

	# JSON to query for failed tests
	failed_tests_query_json = {
		"from":"unittest",
		"where":{
			"and":[
				{"eq":{"repo.changeset.id12":None}},
				{"eq":{"repo.branch.name":analysisbranch}},
				{"prefix":{"run.name":platform_prefix}},
				{"eq":{"task.state":"failed"}},
				{"eq":{"result.ok":"false"}},
				{"or":[{"prefix":{"run.suite":suite}} for suite in seta_suites]}
			]
		},
		"limit":100000,
		"select":[{"name":"test","value":"result.test"}]
	}

	# JSONs to use for per-test test file queries
	mochitest_query_json = {
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

	xpcshell_query_json = {
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

	# Get all patches
	if not changesets:
		changesets = get_changesets(hg_analysisbranch, startrevision, numpatches)

	# Get all pushes
	seta_query = {
		"from":"treeherder",
		"select":{"name": "changeset", "value":"repo.changeset.id12"},
		"limit":1000000,
		"where":{"and":[
			{"in":{"repo.changeset.id12":changesets}},
			{"prefix":{"job.type.name":platform_prefix}},
			{"eq":{"repo.branch.name":analysisbranch}}
		]}
	}

	seta_numtests_data = query_activedata(seta_query, active_data_url='http://activedata.allizom.org/query')
	seta_numtests_dict = {changeset: 0 for changeset in seta_numtests_data['changeset']}

	# Format SETA data (expand to all changesets)
	seta_numtests_expanded = []
	prev_changeset = None
	cset_groups = {}
	cset_group = []

	for changeset in changesets:
		if prev_changeset:
			if prev_changeset != changeset and changeset in seta_numtests_dict:
				# Found a new push, set the new push revision and save cset grouping to
				# make histogram processing simpler.
				cset_groups[prev_changeset] = cset_group.copy()
				cset_group = []

				prev_changeset = changeset
		else:
			prev_changeset = changeset

		seta_numtests_expanded.append((seta_numtests_dict[prev_changeset], changeset))
		cset_group.append(changeset)
	cset_groups[prev_changeset] = cset_group.copy()

	print(cset_groups)

	tests_for_changeset = {}
	tests_per_file = {}

	histogram1_datalist = []
	grouped_data = {}

	# For each patch
	all_changesets = []
	prev_changeset = None
	for count, changeset in enumerate(changesets):
		if prev_changeset:
			if prev_changeset != changeset and changeset in seta_numtests_dict:
				prev_changeset = changeset
		else:
			prev_changeset = changeset

		log.info("On changeset " + "(" + str(count) + "): " + changeset)

		# Get patch
		files_url = HG_URL + hg_analysisbranch + "/json-info/" + changeset
		data = get_http_json(files_url)

		files_modified = data[changeset]['files']

		# Get tests that use this patch
		all_tests = []

		in_entry = {"in": {"source.file.name": files_modified}}
		mochitest_query_json['where']['and'][0] = in_entry
		xpcshell_query_json['where']['and'][0] = in_entry
		failed_tests_query_json['where']['and'][0] = {"eq":{"repo.changeset.id12":changeset}}

		try:
			failed_tests = query_activedata(failed_tests_query_json, active_data_url='http://activedata.allizom.org/query')

			mochi_tests = [testchunk[0] for testchunk in query_activedata(mochitest_query_json)]
			xpc_tests = [testchunk[0] for testchunk in query_activedata(xpcshell_query_json)]
		except Exception as e:
			log.info("Error running query: " + str(mochitest_query_json))
			log.info("or the query: " + str(xpcshell_query_json))
			mochi_tests = []
			xpc_tests = []

		print(failed_tests)
		if 'test' not in failed_tests and changeset in cset_groups:
			log.info("No task failures to compare against.")
			continue

		all_tests = list(set(mochi_tests) | set(xpc_tests))

		if prev_changeset not in grouped_data: 
			grouped_data[prev_changeset] = {}
			grouped_data[prev_changeset]['all_failed_tests'] = []
			grouped_data[prev_changeset]['all_ptc_tests'] = all_tests.copy()

		grouped_data[prev_changeset]['all_ptc_tests'] = list(set(grouped_data[prev_changeset]['all_ptc_tests']) | set(all_tests))

		if 'test' in failed_tests:
			all_failed_tests = [test for test in failed_tests['test'] if test not in exclude_failed_tests]
			grouped_data[prev_changeset]['all_failed_tests'] = list(
				set(grouped_data[prev_changeset]['all_failed_tests']) | set(all_failed_tests)
			)

		all_failed_tests = grouped_data[prev_changeset]['all_failed_tests']
		if len(all_failed_tests) == 0:
			continue

		all_tests = grouped_data[prev_changeset]['all_ptc_tests']

		all_tests_not_run = list(set(all_failed_tests) - set(all_tests))

		log.info("Number of tests: " + str(len(all_tests)))
		log.info("Number of failed tests: " + str(len(all_failed_tests)))
		log.info("Number of files: " + str(len(files_modified)))
		log.info("Number of tests not scheduled by per-test: " + str(len(all_tests_not_run)))
		log.info("")

		tests_for_changeset[changeset] = {}
		tests_for_changeset[changeset]['patch-link'] = HG_URL + analysisbranch + "/rev/" + changeset
		tests_for_changeset[changeset]['numfiles'] = len(files_modified)
		tests_for_changeset[changeset]['numtests'] = len(all_tests)
		tests_for_changeset[changeset]['numtestsfailed'] = len(all_failed_tests)
		tests_for_changeset[changeset]['numtestsnotrun'] = len(all_tests_not_run)
		tests_for_changeset[changeset]['testsnotrun'] = all_tests_not_run

		all_changesets.append(changeset)

	# Recompute histogram
	new_histogram = []
	for changeset in all_changesets:
		for pushcset, grouping in cset_groups.items():
			if changeset not in grouping:
				continue
			min_tests_not_run = min([tests_for_changeset[c]['numtestsnotrun'] for c in grouping if c in tests_for_changeset])
			new_histogram.append(
				(tests_for_changeset[changeset]['numtestsfailed'], tests_for_changeset[changeset]['numtestsfailed'] - min_tests_not_run, changeset)
			)
			break

	## Save results (number, and all tests scheduled)
	if outputdir:
		log.info("\nSaving results to output directory: " + outputdir)
		save_json(tests_for_changeset, outputdir, str(int(time.time())) + '_per_changeset_breakdown.json')

	## Plot the results
	f, b1 = plot_histogram(
		data=[numtestsfailed for numtestsfailed, _, _ in new_histogram],
		x_labels=all_changesets,
		title="Tests scheduled (Y) over all changesets (X)"
	)

	# Plot a second bar on top
	b2 = plt.bar(range(len(all_changesets)), [pertesttests for _, pertesttests, _ in new_histogram])
	plt.legend((b1[0], b2[0]), ('# of failed tests', '# of per-test scheduled tests'))

	log.info("Close figures to end analysis.")
	plt.show()

