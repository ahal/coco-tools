import os
import time
import logging
import numpy as np
import csv
import importlib

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
	get_fixed_by_commit_entries,
	hg_branch,
	format_testname,
	pattern_find,
	HG_URL,
	TYPE_PERTEST,
	TYPE_STDPTC
)

log = logging.getLogger('pertestcoverage')


def import_class(file, classname):
	modname = '.custom_scheduling.{}'.format(file)
	mod = importlib.import_module(modname, package='pertestcoverage.analysistypes')
	customclass = getattr(mod, classname)
	return customclass


def run(args=None, config=None):
	"""
		Expects a `config` with the settings found in
		pertestcoverage/configs/config_fixed_by_commit_rawdata.yml

		Throws errors if something is missing, all the settings
		are listed at the top of the script.

		Expects a custom_script entry like: ['coverage_based']
		where 'coverage_based' refers to a python file in pertestcoverage
		it must contain a class which is passed the YAML configuration when initialized
		with a function named 'analyze_fbc_entry(fbc_entry)'
		and which returns a dict that must contain atleast the following: {'success': True/False, 'skip': True/False}
		ex:
			>> myclass(config=config)
			>> res = myclass.analyze_fbc_entry(fbc_entry)
			>> res
			{'success': False, 'skip': True}
	"""
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")

	numpatches = config['numpatches']
	changesets_list = config['changesets']
	outputdir = config['outputdir']
	analyze_all = config['analyze_all'] if 'analyze_all' in config else False
	mozcentral_path = config['mozcentral_path'] if 'mozcentral_path' in config else None
	runname = config['runname'] if 'runname' in config else None
	include_guaranteed = config['include_guaranteed'] if 'include_guaranteed' in  config else False
	use_active_data = config['use_active_data'] if 'use_active_data' in config else False
	skip_py = config['skip_py'] if 'skip_py' in config else True

	suites_to_analyze = config['suites_to_analyze']
	platforms_to_analyze = config['platforms_to_analyze']
	from_date = config['from_date']

	timestr = str(int(time.time()))

	custom_script = config['custom_scheduling']
	custom_classname = config['custom_classname']
	custom_class = import_class(custom_script, custom_classname)
	custom_class_obj = custom_class(config)

	failed_tests_query_json = {
		"from":"unittest",
		"where":{
			"and":[
				{"eq":{"repo.changeset.id12":None}},
				{"eq":{"repo.branch.name":None}},
				{"eq":{"task.state":"failed"}},
				{"eq":{"result.ok":"false"}},
				{"or":[
					{"regex":{"job.type.name":".*%s.*" % suite}}
					for suite in suites_to_analyze
				]},
				{"or": [
					{"regex":{"job.type.name":".*%s.*" % platform}}
					for platform in platforms_to_analyze
				]},
			]
		},
		"limit":100000,
		"select":[{"name":"test","value":"result.test"}]
	}

	log.info("Getting FBC entries...")

	changesets = get_fixed_by_commit_entries(
		localdata=not use_active_data,
		activedata=use_active_data,
		suites_to_analyze=suites_to_analyze,
		platforms_to_analyze=platforms_to_analyze,
		from_date=from_date,
		local_datasets_list=changesets_list,
		save_fbc_entries=outputdir
	)

	# For each patch
	histogram1_datalist = []
	tests_for_changeset = {}
	changesets_counts = {}
	count_changesets_processed = 0
	all_changesets = []

	for count, tp in enumerate(changesets):
		if count_changesets_processed >= numpatches:
			continue

		if len(tp) == 4:
			changeset, suite, repo, test_fixed = tp
		else:
			continue

		orig_test_fixed = test_fixed
		test_fixed = test_fixed.split('ini:')[-1]
		if 'mochitest' not in suite and 'xpcshell' not in suite:
			test_fixed = format_testname(test_fixed)

		changeset = changeset[:12]

		log.info("")
		log.info("On changeset " + "(" + str(count) + "): " + changeset)
		log.info("Running analysis: %s" % str(runname))
		log.info("Test name: %s" % test_fixed)

		# Get patch
		currhg_analysisbranch = hg_branch(repo)
		files_url = HG_URL + currhg_analysisbranch + "json-info/" + changeset
		data = get_http_json(files_url)
		files_modified = data[changeset]['files']
		orig_files_modified = files_modified.copy()

		# Get tests that use this patch
		failed_tests_query_json['where']['and'][0] = {"eq": {"repo.changeset.id12": changeset}}
		failed_tests_query_json['where']['and'][1] = {"eq": {"repo.branch.name": repo}}

		log.info("Checking for test failures...")

		all_tests = []
		failed_tests = []
		try:
			failed_tests = query_activedata(failed_tests_query_json)
		except Exception as e:
			log.info("Error running query: " + str(failed_tests_query_json))

		all_failed_tests = []
		if 'test' in failed_tests:
			all_failed_tests = [test for test in failed_tests['test']]

		if pattern_find(test_fixed, all_failed_tests):
			log.info("Test was not completely fixed by commit: " + str(test_fixed))
			continue

		log.info("Test was truly fixed. Failed tests: " + str(all_failed_tests))

		# Perform scheduling
		all_tests_not_run = []
		returned_data = custom_class_obj.analyze_fbc_entry(
			(changeset, suite, repo, orig_test_fixed),
			test_fixed
		)

		if 'skip' in returned_data and returned_data['skip']:
			continue
		if not returned_data['success']:
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
			'patch-link': HG_URL + currhg_analysisbranch + "rev/" + changeset,
			'numfiles': len(files_modified),
			'numtests': len(all_tests),
			'numtestsfailed': 1,
			'numtestsnotrun': len(all_tests_not_run),
			'files_modified': files_modified,
			'suite': suite,
			'runname': runname,
			'orig-test-related': orig_test_fixed,
			'test-related': test_fixed,
			'testsnotrun': all_tests_not_run,
		}

		for entry in returned_data:
			tests_for_changeset[entry] = returned_data[entry]

		all_changesets.append(changeset)
		histogram1_datalist.append((1, 1-len(all_tests_not_run), changeset))
		count_changesets_processed += 1

		numchangesets = len(all_changesets)
		total_correct = sum([
				1 if not tests_for_changeset[cset + "_" + str(cset_count)]['testsnotrun'] else 0
				for cset in all_changesets
		])
		log.info("Running success rate = {:3.2f}%".format(float((100 * (total_correct/numchangesets)))))

	log.info("")

	## Save results (number, and all tests scheduled)
	if outputdir:
		log.info("\nSaving results to output directory: " + outputdir)
		timestr = str(int(time.time()))
		save_json(tests_for_changeset, outputdir, timestr + '_per_changeset_breakdown.json')

	f = plt.figure()

	numchangesets = len(all_changesets)
	total_correct = sum([
			1 if not tests_for_changeset[cset + "_1"]['testsnotrun'] else 0
			for cset in all_changesets
	])
	total_incorrect = sum([
			1 if tests_for_changeset[cset + "_1"]['testsnotrun'] else 0
			for cset in all_changesets
	])

	b2 = plt.pie(
		[
			100 * (total_correct/numchangesets),
			100 * (total_no_coverage_data/numchangesets)
		],
		colors=['green', 'red'],
		labels=[
			'Successfully scheduled',
			'Not successfully scheduled'
		],
		autopct='%1.1f%%'
	)

	plt.legend()

	log.info("Completed analysis for run: %s" % str(runname))

	log.info("Total number of changesets in pie chart: " + str(numchangesets))

	log.info("Close figures to end analysis.")
	log.info("Changesets analyzed (use these in other analysis types if possible): \n" + str(all_changesets))
	plt.show()

