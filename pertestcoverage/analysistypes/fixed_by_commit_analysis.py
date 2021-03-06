import os
import time
import logging
import numpy as np
import csv

from matplotlib import pyplot as plt

from ..cli import AnalysisParser

from ..utils.cocoload import (
	save_json,
	get_http_json,
	query_activedata,
	get_changesets,
	get_coverage_tests,
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

			# To limit number of patchs if there's a lot
			numpatches: 100
			outputdir: "C:/tmp/"
			hg_analysisbranch:
				mozilla-central: "mozilla-central"
				mozill-inboun: "integration/mozilla-inbound"

			# See 'config/config_fixed_by_commit_analysis.yml' for more info on the
			# following field.
			changesets: ["path_to_csv_with_data"]

			tc_tasks_rev_n_branch: [
				["dcb3a3ba9065", "try"],
				["6369d1c6526b", "try"]
			]
	"""
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")

	numpatches = config['numpatches']
	hg_analysisbranch = config['hg_analysisbranch']
	changesets_list = config['changesets']
	outputdir = config['outputdir']
	tc_tasks_rev_n_branch = config['tc_tasks_rev_n_branch']

	changesets = []
	for csets_csv_path in changesets_list:
		with open(csets_csv_path, 'r') as f:
			reader = csv.reader(f)
			count = 0
			for row in reader:
				if count == 0:
					count += 1
					continue
				changesets.append(tuple(row))

	# JSONs to use for per-test test file queries
	coverage_query = {
		"from":"coverage",
		"where":{"and":[
			{"in":{"repo.changeset.id12":[rev for rev, branch in tc_tasks_rev_n_branch]}},
			{"eq":{"repo.branch.name":"try"}},
			{"eq":{"test.name":""}}
		]},
		"limit":1,
		"groupby":[{"name":"source","value":"source.file.name"}]
	}

	failed_tests_query_json = {
		"from":"unittest",
		"where":{
			"and":[
				{"eq":{"repo.changeset.id12":None}},
				{"eq":{"repo.branch.name":None}},
				{"prefix":{"run.name":"test-linux64"}},
				{"eq":{"task.state":"failed"}},
				{"eq":{"result.ok":"false"}},
				{
					"or":[
						{"prefix":{"run.suite":"mochitest"}},
						{"prefix":{"run.suite":"xpcshell"}}
					]
				}
			]
		},
		"limit":100000,
		"select":[{"name":"test","value":"result.test"}]
	}

	all_failed_ptc_tests = get_coverage_tests(tc_tasks_rev_n_branch, get_failed=True)

	tests_for_changeset = {}
	changesets_counts = {}
	tests_per_file = {}

	histogram1_datalist = []

	# For each patch
	all_changesets = []
	for count, tp in enumerate(changesets):
		if count >= numpatches:
			continue

		if len(tp) == 4:
			changeset, _, repo, test_fixed = tp
		else:
			cov_exists, status, code, changeset, _, repo, test_fixed, _ = tp

			if cov_exists == 'no':
				continue

		changeset = changeset[:12]

		log.info("On changeset " + "(" + str(count) + "): " + changeset)

		# Get patch
		currhg_analysisbranch = hg_analysisbranch[repo]
		files_url = HG_URL + currhg_analysisbranch + "/json-info/" + changeset
		data = get_http_json(files_url)

		files_modified = data[changeset]['files']

		# Get tests that use this patch
		failed_tests_query_json['where']['and'][0] = {"eq": {"repo.changeset.id12": changeset}}
		failed_tests_query_json['where']['and'][1] = {"eq": {"repo.branch.name": repo}}

		all_tests = []

		try:
			failed_tests = query_activedata(failed_tests_query_json)
			all_tests = get_coverage_tests(tc_tasks_rev_n_branch, get_files=files_modified)
		except Exception as e:
			log.info("Error running query: " + str(test_coverage_query_json))

		all_failed_tests = []
		if 'test' in failed_tests:
			all_failed_tests = [test for test in failed_tests['test']]

		if test_fixed in all_failed_tests:
			log.info("Test was not completely fixed by commit: " + str(test_fixed))
			continue
		else:
			log.info("Test was truly fixed. Failed tests: " + str(all_failed_tests))

		all_tests_not_run = list(set([test_fixed]) - set(all_tests))

		log.info("Number of tests: " + str(len(all_tests)))
		log.info("Number of failed tests: " + str(len([test_fixed])))
		log.info("Number of files: " + str(len(files_modified)))
		log.info("Number of tests not scheduled by per-test: " + str(len(all_tests_not_run)))
		log.info("Tests not scheduled: \n" + str(all_tests_not_run))

		cset_count = 1
		if changeset not in changesets_counts:
			changesets_counts[changeset] = cset_count
		else:
			changesets_counts[changeset] += 1
			cset_count = changesets_counts[changeset]

		changeset_name = changeset + "_" + str(cset_count)
		tests_for_changeset[changeset_name] = {}
		tests_for_changeset[changeset_name]['patch-link'] = HG_URL + currhg_analysisbranch + "/rev/" + changeset
		tests_for_changeset[changeset_name]['numfiles'] = len(files_modified)
		tests_for_changeset[changeset_name]['numtests'] = len(all_tests)
		tests_for_changeset[changeset_name]['numtestsfailed'] = 1
		tests_for_changeset[changeset_name]['numtestsnotrun'] = len(all_tests_not_run)
		tests_for_changeset[changeset_name]['reasons_not_run'] = '' if len(all_tests_not_run) == 0 else 'unknown'
		tests_for_changeset[changeset_name]['files_modified'] = files_modified
		tests_for_changeset[changeset_name]['testsnotrun'] = all_tests_not_run

		for test in all_tests_not_run:
			if test in all_failed_ptc_tests:
				tests_for_changeset[changeset_name]['reasons_not_run'] = 'failed_test'
				continue
			
			coverage_query['where']['and'][2]['eq']['test.name'] = test_fixed
			coverage_data = query_activedata(coverage_query)
			if len(coverage_data) == 0:
				tests_for_changeset[changeset_name]['reasons_not_run'] =  'no_coverage_for_test'
				continue
  
		log.info("Reason not run (if any): " + tests_for_changeset[changeset_name]['reasons_not_run'])
		log.info("")

		all_changesets.append(changeset)
		histogram1_datalist.append((1, 1-len(all_tests_not_run), changeset))


	## Save results (number, and all tests scheduled)
	if outputdir:
		log.info("\nSaving results to output directory: " + outputdir)
		save_json(tests_for_changeset, outputdir, str(int(time.time())) + '_per_changeset_breakdown.json')

	## Plot the results
	f, b1 = plot_histogram(
		data=[numtestsfailed for numtestsfailed, _, _ in histogram1_datalist],
		x_labels=all_changesets,
		title="Tests scheduled (Y) over all changesets (X)"
	)

	# Plot a second bar on top
	b2 = plt.bar(range(len(all_changesets)), [pertesttests for _, pertesttests, _ in histogram1_datalist])

	b3 = plt.bar(
		range(len(all_changesets)),
		[
			1 if tests_for_changeset[cset + "_1"]['reasons_not_run'] == 'no_coverage_for_test' else 0
			for cset in all_changesets
		],
		color='red'
	)

	b4 = plt.bar(
		range(len(all_changesets)),
		[
			1 if tests_for_changeset[cset + "_1"]['reasons_not_run'] == 'failed_test' else 0
			for cset in all_changesets
		],
		color='black'
	)

	plt.legend(
		(b1[0], b2[0], b3[0], b4[0]),
		(
			'# of failed tests',
			'# of per-test scheduled tests',
			'No coverage for test',
			'Test failed on try runs'
		)
	)

	log.info("Close figures to end analysis.")
	log.info("Changesets analyzed (use these in other analysis types if possible): \n" + str(all_changesets))
	plt.show()

