'''

	These functions are used to categorize scheduling
	failures in various analysis types and result in a JSON
	output named '*_per_changeset_breakdown.json'. Entries
	in the file must also contain: 'testsnotrun', and
	'files_modified'.

'''
import logging

from ..cocofilter import (
	find_support_files_modified,
	find_files_in_changeset
)
from ..cocoload import pattern_find

log = logging.getLogger('pertestcoverage')


def visualize_category_data(ptc_breakdown_datalist, **kwargs):
	for argument, value in kwargs.items():
		if argument in VISUALIZATIONS and value:
			VISUALIZATIONS[argument](ptc_breakdown_datalist, **kwargs)


def categorize_data(ptc_breakdown_datalist, functname, **kwargs):
	categ_data = NAME2FUNCT[functname](ptc_breakdown_datalist, **kwargs)
	return categ_data


def find_failed_changesets(data):
	new_data_list = {}
	for changeset, info in data.items():
		if info['testsnotrun']:
			new_data_list[changeset] = info
	return new_data_list


def find_failed_changesets_list(datalist):
	failed_ptc_data = []
	for data in datalist:
		failed_ptc_data.append(find_failed_changesets(data))
	return failed_ptc_data


def categorize_failed(ptc_breakdown_datalist, use_failed=True, **kwargs):
	return find_failed_changesets_list(ptc_breakdown_datalist)


def is_js_file(file):
	if '.js' in file and not file.endswith('.json'):
		return True
	return False


def js_file_exists(ptc_info):
	fmod = ptc_info['files_modified']
	for f in fmod:
		if is_js_file(f):
			return True
	return False


def categorize_js_changes(ptc_breakdown_datalist, use_failed=True, **kwargs):
	'''Returns changesets which have JS changes.'''
	new_data_list = []

	failed_ptc_data = ptc_breakdown_datalist
	if use_failed:
		failed_ptc_data = find_failed_changesets_list(ptc_breakdown_datalist)

	for data in failed_ptc_data:
		new_data_list.append(
			{
				cset: info
				for cset, info in data.items()
				if js_file_exists(info)
			}
		)

	return new_data_list


def is_c_file(file):
	if '.cpp' in file or file.endswith('.h') or file.endswith('.c'):
		return True
	return False


def c_file_exists(ptc_info, exclusive=False):
	fmod = ptc_info['files_modified']
	for f in fmod:
		if is_c_file(f):
			if not exclusive:
				# Found a c-file and we are
				return True
		elif exclusive: # Changeset must have only c-changes
			return False
	if exclusive:
		return True
	return False


def categorize_c_changes(ptc_breakdown_datalist, use_failed=True, exclusive=False, **kwargs):
	'''Returns changesets which have C/C++ changes.'''
	new_data_list = []

	failed_ptc_data = ptc_breakdown_datalist
	if use_failed:
		failed_ptc_data = find_failed_changesets_list(ptc_breakdown_datalist)

	for data in failed_ptc_data:
		new_data_list.append(
			{
				cset: info
				for cset, info in data.items()
				if c_file_exists(info, exclusive=exclusive)
			}
		)

	return new_data_list


def categorize_unlreated(ptc_breakdown_datalist, use_failed=True, **kwargs):
	'''
		All changesets which do not fit in the other categories -
		the other cases are computed to find this information.
	'''
	unrelated_data = []

	failed_ptc_data = ptc_breakdown_datalist
	if use_failed:
		failed_ptc_data = find_failed_changesets_list(ptc_breakdown_datalist)

	c_data = [d.keys() for d in categorize_c_changes(failed_ptc_data, use_failed=False)]
	js_data = [d.keys() for d in categorize_js_changes(failed_ptc_data, use_failed=False)]
	test_data = [
		d.keys()
		for d in categorize_test_changes(failed_ptc_data, use_failed=False, **kwargs)
	]

	for num_entry, data in enumerate(failed_ptc_data):
		unrelated_entries = list(
			set(data.keys()) - \
			(
				set(c_data[num_entry]) | \
				set(js_data[num_entry]) | \
				set(test_data[num_entry])
			)
		)

		unrelated_data.append(
			{
				cset: failed_ptc_data[num_entry][cset]
				for cset in unrelated_entries
			}
		)

	return unrelated_data


def categorize_directory_match(
		ptc_breakdown_datalist,
		use_failed=True,
		levels_to_match=1,
		level_splitter='/',
		list_failures_not_matched=False,
		**kwargs
	):

	directory_matched_data = []

	failed_ptc_data = ptc_breakdown_datalist
	if use_failed:
		failed_ptc_data = find_failed_changesets_list(ptc_breakdown_datalist)

	for num_entry, data in enumerate(failed_ptc_data):
		if len(data) == 0:
			continue

		fentry = list(data.values())[0]
		if 'testsnotrun' not in fentry or 'files_modified' not in fentry:
			continue

		tmp_result = []
		for cset, info in data.items():
			if len(info['testsnotrun']) == 0:
				continue

			test = info['testsnotrun'][0]
			test_levels = '/'.join(test.split(level_splitter)[0:levels_to_match])

			for file in info['files_modified']:
				if test_levels in file or file in test_levels:
					tmp_result.append(cset)
					failed_ptc_data[num_entry][cset]['dir-match'] = True
					break

		directory_matched_data.append({
			cset: failed_ptc_data[num_entry][cset]
			for cset in tmp_result
		})

		if list_failures_not_matched:
			unmatched = set(list(failed_ptc_data[num_entry].keys())) - set(tmp_result)
			for cset in unmatched:
				if len(failed_ptc_data[num_entry][cset]['testsnotrun']) == 0:
					continue
				log.info("")
				log.info(
					"Test not matched: %s" % \
					failed_ptc_data[num_entry][cset]['testsnotrun'][0]
				)
				log.info(
					"Files modified: \n %s" % \
					str('\n'.join(['\t' + f for f in failed_ptc_data[num_entry][cset]['files_modified']]))
				)

	return directory_matched_data


def find_test_related(data, mozpath=None, return_keys=False):
	'''
		Returns all changesets with test-related changes.
	'''
	new_data = {}

	for cset, info in data.items():
		files_modified = info['files_modified'].copy()
		orig_files = files_modified.copy()
		testsnotrun = info['testsnotrun']

		support_files = []
		for test in testsnotrun:
			if mozpath:
				support_files = find_support_files_modified(files_modified, test, mozpath)

		files_modified = list(set(files_modified) - set(support_files))
		files_modified = [
			f for f in files_modified
			if '/test/' not in f and '/tests/' not in f and 'testing/' not in f
		]

		if 'repo' in info:
			new, _, _ = find_files_in_changeset(cset, info['repo'])
			new = [n.lstrip('/') for n in new]
			files_modified = list(set(files_modified) - set(new))

		if len(orig_files) != len(files_modified):
			new_data[cset] = info

	if return_keys:
		return new_data.keys()
	return new_data


def categorize_test_changes(
		ptc_breakdown_datalist,
		use_failed=True,
		**kwargs
	):
	'''
		This looks through all changesets where a scheduling failure
		occurred and returns a list of lists of changesets
		who failed and have test related changes within them.

		Includes changesets with non-test-related files changed
		unles 'use_failed' is set to False.
	'''
	new_datalist = []

	failed_ptc_data = ptc_breakdown_datalist
	if use_failed:
		failed_ptc_data = find_failed_changesets_list(ptc_breakdown_datalist)

	mozpath = kwargs.get('mozcentral_path', None)
	for data in failed_ptc_data:
		new_datalist.append(find_test_related(data, mozpath=mozpath))

	return new_datalist


def visualize_all(categ_data, show_files_modified=False, **kwargs):
	for categ_item in categ_data:
		categ_item['count'] = [
			len(data.keys())
			for data in categ_item['data']
		]

		log.info(
			"For category %s, number of changesets found: %s" %
			(categ_item['category'], sum(categ_item['count']))
		)

		if show_files_modified:
			files_modified = []
			for data in categ_item['data']:
				for key, info in data.items():
					files_modified.extend(info['files_modified'])
			log.info(
				"Files modified: \n %s" % \
				str('\n'.join(['\t' + f for f in files_modified]))
			)

	return


def visualize_by_suites(categ_data, suite_splitter=['', 0], sort_into_suites=[], **kwargs):
	# Breakdown categ_data into a dict keyed by suite
	suites_dict = {}
	for categ_item in categ_data:
		ptc_breakdown_datalist = categ_item['data']
		for ptc_breakdown in ptc_breakdown_datalist:
			if len(ptc_breakdown) == 0:
				continue
			if 'suite' not in ptc_breakdown[list(ptc_breakdown.keys())[0]]:
				continue

			category = categ_item['category']
			for cset, ptc_info in ptc_breakdown.items():
				suite = ptc_info['suite'].split(suite_splitter[0])[suite_splitter[1]]
				if sort_into_suites:
					res = pattern_find(suite, sort_into_suites)
					if res:
						suite = res
					else:
						continue
				if suite not in suites_dict:
					suites_dict[suite] = {}
				if category not in suites_dict[suite]:
					suites_dict[suite][category] = []
				suites_dict[suite][category].append((cset, ptc_info))

	new_suites_dict = {}
	for suite in suites_dict:

		new_suites_dict[suite] = []
		for category in suites_dict[suite]:

			fmtd_entries = {}
			for entry in suites_dict[suite][category]:
				fmtd_entries[entry[0]] = entry[1]

			new_suites_dict[suite].append({
				'category': category,
				'data': [fmtd_entries]
			})

	log.info('\n')
	for suite in new_suites_dict:
		log.info('Visualizing suite: %s' % suite)
		visualize_all(new_suites_dict[suite], **kwargs)

		log.info('\n')


def visualize_by_tests(
		categ_data,
		sort_into_tests=[],
		test_splitter=('***', 0),
		visualize_by_suite=False,
		**kwargs
	):

	# Breakdown into tests
	tests_dict = {}
	for categ_item in categ_data:
		ptc_breakdown_datalist = categ_item['data']
		for ptc_breakdown in ptc_breakdown_datalist:
			if len(ptc_breakdown) == 0:
				continue
			if 'testsnotrun' not in list(ptc_breakdown.values())[0]:
				continue

			category = categ_item['category']
			for cset, ptc_info in ptc_breakdown.items():
				if not ptc_info['testsnotrun']:
					continue

				test = ptc_info['testsnotrun'][0].split(test_splitter[0])[test_splitter[1]]
				if sort_into_tests:
					res = pattern_find(test, sort_into_tests)
					if res:
						test = res
					else:
						continue
				if test not in tests_dict:
					tests_dict[test] = {}
				if category not in tests_dict[test]:
					tests_dict[test][category] = []

				tests_dict[test][category].append((cset, ptc_info))

	new_tests_dict = {}
	for test in tests_dict:

		new_tests_dict[test] = []
		for category in tests_dict[test]:

			fmtd_entries = {}
			for entry in tests_dict[test][category]:
				fmtd_entries[entry[0]] = entry[1]

			new_tests_dict[test].append({
				'category': category,
				'data': [fmtd_entries]
			})

	log.info('\n')
	for test in new_tests_dict:
		log.info('Visualizing test: %s' % test)
		if visualize_by_suite:
			visualize_by_suites(new_tests_dict[test], **kwargs)
		else:
			visualize_all(new_tests_dict[test], **kwargs)

		log.info('\n')


VISUALIZATIONS = {
	'visualize_all': visualize_all,
	'visualize_by_suite': visualize_by_suites,
	'visualize_by_test': visualize_by_tests
}


NAME2FUNCT = {
	'failed-changes': categorize_failed,
	'js-changes': categorize_js_changes,
	'c-changes': categorize_c_changes,
	'unlreated-changes': categorize_unlreated,
	'test-changes': categorize_test_changes,
	'dir-match': categorize_directory_match
}