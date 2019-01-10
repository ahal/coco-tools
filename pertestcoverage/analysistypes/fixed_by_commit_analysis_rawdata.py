import os
import time
import logging
import numpy as np
import csv

from matplotlib import pyplot as plt

from ..cli import AnalysisParser

from ..utils.cocofilter import (
	fix_names,
	find_files_in_changeset,
	find_support_files_modified,
	filter_per_test_tests,
	get_tests_with_no_data
)

from ..utils.cocoload import (
	save_json,
	get_http_json,
	query_activedata,
	get_changesets,
	get_coverage_tests,
	get_coverage_tests_from_jsondatalist,
	get_all_pertest_data,
	get_all_stdptc_data,
	format_testname,
	pattern_find,
	HG_URL,
	TYPE_PERTEST,
	TYPE_STDPTC
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
		Expects a `config` with the settings found in
		pertestcoverage/configs/config_fixed_by_commit_rawdata.yml

		Throws errors if something is missing, all the settings
		are listed at the top of the script.
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
	pertest_rawdata_folders = config['pertest_rawdata_folders']
	analyze_all = config['analyze_all'] if 'analyze_all' in config else False
	mozcentral_path = config['mozcentral_path'] if 'mozcentral_path' in config else None
	runname = config['runname'] if 'runname' in config else None
	include_guaranteed = config['include_guaranteed'] if 'include_guaranteed' in  config else False
	use_active_data = config['use_active_data'] if 'use_active_data' in config else False
	skip_py = config['skip_py'] if 'skip_py' in config else True

	#if use_active_data:
	suites_to_analyze = config['suites_to_analyze']
	platforms_to_analyze = config['platforms_to_analyze']
	from_date = config['from_date']

	timestr = str(int(time.time()))

	# JSONs to use for per-test test file queries
	coverage_query = {
		"from":"coverage",
		"where":{"and":[
			{"eq":{"repo.branch.name":"mozilla-central"}},
			{"regexp":{"test.name":""}},
			{"exists":"test.name"}
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

	changesets = get_fixed_by_commit_entries(
		localdata=not use_active_data,
		activedata=use_active_data,
		suites_to_analyze=suites_to_analyze,
		platforms_to_analyze=platforms_to_analyze,
		from_date=from_date,
		local_datasets_list=changesets_list,
		save_fbc_entries=outputdir
	)

	jsondatalist = []
	if not use_active_data:
		for location_entry in pertest_rawdata_folders:
			log.info("Opening data from %s" % location_entry)
			if location_entry['type'] == TYPE_PERTEST:
				print('here')
				jsondatalist.extend(get_all_pertest_data(location_entry['location'], chrome_map_path=location_entry['chrome-map']))
			elif location_entry['type'] == TYPE_STDPTC:
				print('here2')
				jsondatalist.extend(get_all_stdptc_data(location_entry['location'], chrome_map_path=location_entry['chrome-map']))

	all_failed_ptc_tests = get_coverage_tests(tc_tasks_rev_n_branch, get_failed=True)

	tests_for_changeset = {}
	changesets_counts = {}
	tests_per_file = {}

	histogram1_datalist = []

	# Remove tests with no data 
	tmp_tests = []
	for count, tp in enumerate(changesets):
		if len(tp) == 4:
			changeset, suite, repo, test_fixed = tp
		else:
			cov_exists, status, code, changeset, suite, repo, test_fixed, _ = tp

		test_fixed = test_fixed.split('ini:')[-1]
		if 'mochitest' not in suite and 'xpcshell' not in suite:
			test_fixed = format_testname(test_fixed)
		else:
			test_fixed = format_testname(test_fixed, wpt=False)
		tmp_tests.append(test_fixed)

	tests_with_no_data = []
	if not use_active_data:
		tests_with_no_data = get_tests_with_no_data(jsondatalist, tmp_tests)
	else:
		for test_matcher in tmp_tests:
			coverage_query['where']['and'][1]['regexp']['test.name'] = ".*" + test_matcher.replace('\\', '/') + ".*"
			log.info("Querying active data for data for the test: %s" % test_matcher.replace('\\', '/'))
			coverage_data = query_activedata(coverage_query)
			if len(coverage_data) == 0:
				log.info("Found no data.\n")
				tests_with_no_data.append(test_matcher)
			else:
				log.info("Found data. \n")

	log.info("Number of tests with no data: %s" % str(len(tests_with_no_data)))
	log.info("Number of tests in total: %s" % str(len(tmp_tests)))

	if outputdir:
		save_json(
			{
				'testswithnodata': fix_names(changesets, tests_with_no_data),
				'orig_testswithnodata': tests_with_no_data,
				'alltests-matchers': tmp_tests,
			},
			outputdir,
			timestr + '_test_matching_info.json'
		)

	# For each patch
	changesets_removed = {}
	count_changesets_processed = 0
	all_changesets = []
	num_guaranteed = 0
	for count, tp in enumerate(changesets):
		if count_changesets_processed >= numpatches:
			continue

		if len(tp) == 4:
			changeset, suite, repo, test_fixed = tp
		else:
			cov_exists, status, code, changeset, suite, repo, test_fixed, _ = tp

			if 'test' in status:
				continue

		if skip_py and test_fixed.endswith('.py'):
			# Skip all python tests.
			continue

		orig_test_fixed = test_fixed
		test_fixed = test_fixed.split('ini:')[-1]
		if 'mochitest' not in suite and 'xpcshell' not in suite:
			test_fixed = format_testname(test_fixed)

		found_bad = False
		for t in tests_with_no_data:
			if test_fixed in t or t in test_fixed:
				found_bad = True
				break
		if found_bad:
			continue

		changeset = changeset[:12]

		log.info("")
		log.info("On changeset " + "(" + str(count) + "): " + changeset)
		log.info("Running analysis: %s" % str(runname))
		log.info("Test name: %s" % test_fixed)

		# Get patch
		currhg_analysisbranch = hg_analysisbranch[repo]
		files_url = HG_URL + currhg_analysisbranch + "/json-info/" + changeset
		data = get_http_json(files_url)
		files_modified = data[changeset]['files']
		orig_files_modified = files_modified.copy()

		# Filter modified files to only exclude all test or test helper files
		if not analyze_all:
			support_files = []
			if mozcentral_path:
				support_files = find_support_files_modified(files_modified, test_fixed, mozcentral_path)
				log.info("Support-files found in files modified: " + str(support_files))

			files_modified = list(set(files_modified) - set(support_files))
			files_modified = [
				f for f in files_modified
				if '/test/' not in f and '/tests/' not in f and 'testing/' not in f
			]

			# We don't have coverage on new files
			new, _, _ = find_files_in_changeset(changeset, repo)
			new = [n.lstrip('/') for n in new]
			files_modified = list(set(files_modified) - set(new))

			if len(files_modified) == 0:
				changesets_removed[changeset] = {}
				changesets_removed[changeset]['support/test files modified'] = orig_files_modified
				log.info("No files modified after filtering test-only or support files.")
				if include_guaranteed:
					num_guaranteed += 1

					cset_count = 1
					if changeset not in changesets_counts:
						changesets_counts[changeset] = cset_count
					else:
						changesets_counts[changeset] += 1
						cset_count = changesets_counts[changeset]

					changeset_name = changeset + "_" + str(cset_count)
					tests_for_changeset[changeset_name] = {
						'patch-link': HG_URL + currhg_analysisbranch + "/rev/" + changeset,
						'numfiles': len(orig_files_modified),
						'numtests': 1,
						'numtestsfailed': 1,
						'numtestsnotrun': len(all_tests_not_run),
						'reasons_not_run': '',
						'files_modified': orig_files_modified,
						'suite': suite,
						'runname': runname,
						'orig-test-related': orig_test_fixed,
						'test-related': test_fixed,
						'testsnotrun': [],
					}
				continue

			files_modified = [
				f for f in files_modified
				if ('.js' in f and not f.endswith('.json')) or \
				   '.cpp' in f or f.endswith('.h') or f.endswith('.c')
			]
			if len(files_modified) == 0:
				log.info("No files left after removing unrelated changes.")
				continue

		# Get tests that use this patch
		failed_tests_query_json['where']['and'][0] = {"eq": {"repo.changeset.id12": changeset}}
		failed_tests_query_json['where']['and'][1] = {"eq": {"repo.branch.name": repo}}

		all_tests = []
		failed_tests = []
		try:
			failed_tests = query_activedata(failed_tests_query_json)
		except Exception as e:
			log.info("Error running query: " + str(failed_tests_query_json))

		if use_active_data:
			try:
				all_tests = get_coverage_tests(tc_tasks_rev_n_branch, get_files=files_modified)
			except Exception as e:
				log.info("Error getting coverage from active data...")
				log.info(str(e))
		else:
			all_tests = get_coverage_tests_from_jsondatalist(jsondatalist, get_files=files_modified)

		all_failed_tests = []
		if 'test' in failed_tests:
			all_failed_tests = [test for test in failed_tests['test']]

		if pattern_find(test_fixed, all_failed_tests):
			log.info("Test was not completely fixed by commit: " + str(test_fixed))
			continue

		log.info("Test was truly fixed. Failed tests: " + str(all_failed_tests))

		found = False
		all_tests_not_run = []
		for test in all_tests:
			if test_fixed in test:
				test_fixed = test
				found = True
				break
		if not found:
			all_tests_not_run.append(test_fixed)

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
		tests_for_changeset[changeset_name] = {
			'patch-link': HG_URL + currhg_analysisbranch + "/rev/" + changeset,
			'numfiles': len(files_modified),
			'numtests': len(all_tests),
			'numtestsfailed': 1,
			'numtestsnotrun': len(all_tests_not_run),
			'reasons_not_run': '' if len(all_tests_not_run) == 0 else 'no_coverage_link_with_test',
			'files_modified': files_modified,
			'suite': suite,
			'runname': runname,
			'orig-test-related': orig_test_fixed,
			'test-related': test_fixed,
			'testsnotrun': all_tests_not_run,
		}

		if use_active_data:
			for test in all_tests_not_run:
				if test in all_failed_ptc_tests:
					tests_for_changeset[changeset_name]['reasons_not_run'] = 'failed_test'
					continue

		log.info("Reason not run (if any): " + tests_for_changeset[changeset_name]['reasons_not_run'])

		all_changesets.append(changeset)
		histogram1_datalist.append((1, 1-len(all_tests_not_run), changeset))
		count_changesets_processed += 1

		numchangesets = len(all_changesets) + num_guaranteed
		total_correct = sum([
				1 if not tests_for_changeset[cset + "_1"]['reasons_not_run'] else 0
				for cset in all_changesets
		]) + num_guaranteed
		log.info("Running success rate = {:3.2f}%".format(float((100 * (total_correct/numchangesets)))))

	log.info("")

	## Save results (number, and all tests scheduled)
	if outputdir:
		log.info("\nSaving results to output directory: " + outputdir)
		timestr = str(int(time.time()))
		save_json(tests_for_changeset, outputdir, timestr + '_per_changeset_breakdown.json')
		save_json(changesets_removed, outputdir, timestr + '_changesets_with_only_test_or_support_files.json')

	# Plot a second bar on top
	f = plt.figure()

	numchangesets = len(all_changesets) + num_guaranteed
	total_correct = sum([
			1 if not tests_for_changeset[cset + "_1"]['reasons_not_run'] else 0
			for cset in all_changesets
	]) + num_guaranteed
	total_no_coverage_data = sum([
			1 if tests_for_changeset[cset + "_1"]['reasons_not_run'] == 'no_coverage_json_for_test' else 0
			for cset in all_changesets
	])
	total_no_coverage_link = sum([
			1 if tests_for_changeset[cset + "_1"]['reasons_not_run'] == 'no_coverage_link_with_test' else 0
			for cset in all_changesets
	])

	b2 = plt.pie(
		[
			100 * (total_correct/numchangesets),
			100 * (total_no_coverage_data/numchangesets) + 100 * (total_no_coverage_link/numchangesets)
		],
		colors=['green', 'red'],
		labels=[
			'Successfully scheduled with per-test coverage data',
			'Not successfully scheduled'
		],
		autopct='%1.1f%%'
	)

	plt.legend()

	f2 = plt.figure()

	b2 = plt.pie(
		[
			100 * (total_correct/numchangesets),
			100 * (total_no_coverage_data/numchangesets),
			100 * (total_no_coverage_link/numchangesets)
		],
		colors=['green', 'red', 'orange'],
		labels=[
			'Successfully scheduled with per-test coverage data',
			'No data found in treeherder',
			'No coverage link between source files modified and test fixed'
		],
		autopct='%1.1f%%'
	)

	plt.legend()

	log.info("Completed analysis for run: %s" % str(runname))

	log.info("Total number of changesets in pie chart: " + str(numchangesets))

	log.info("Close figures to end analysis.")
	log.info("Changesets analyzed (use these in other analysis types if possible): \n" + str(all_changesets))
	plt.show()

