import copy
from cocoload import pattern_find


def filter_per_test_sources(json_data_list, source_matchers):
	filtered_data_list = []
	for per_test_data in json_data_list:
		new_sourcefiles = copy.deepcopy(per_test_data)
		for source in per_test_data['source_files']:
			if pattern_find(source, source_matchers):
				new_sourcefiles[source] = per_test_data['source_files'][source]
		if len(new_sourcefiles) > 0:
			per_test_data['source_files'] = new_sourcefiles
			filtered_data_list.append(per_test_data)
	return filtered_data_list


def filter_per_test_tests(json_data_list, test_matchers):
	filtered_data_list = []
	for per_test_data in json_data_list:
		if pattern_find(per_test_data['test'], test_matchers):
			filtered_data_list.append(per_test_data)
	return filtered_data_list


def filter_per_test_all(json_data_list, test_matchers, source_matchers):
	filtered_tests = filter_per_test_tests(json_data_list, test_matchers)
	filtered_sources = filter_per_test_sources(filtered_tests, source_matchers)
	return filtered_sources


def split_file_types(json_data_list):
	# Splits data into c/c++, js, and etc.
	# groups. The tests are split into their
	# own tests with the 'test' name append
	# with either '-c', '-js', or '-etc'
	# (even if they are empty).
	c_group = ('cpp', 'h', 'c', 'cc', 'hh', 'tcc')
	js_group = ('js', 'jsm')

	split_data = []
	for per_test_data in json_data_list:
		test_name = per_test_data['test']

		c_split = {}
		js_split = {}
		etc_split = {}
		for source in per_test_data['source_files']:
			coverage = per_test_data['source_files'][source]
			source_ftype = source.split('.')[-1]
			if source_ftype in c_group:
				c_split[source] = coverage
			elif source_ftype in js_group:
				js_split[source] = coverage
			else:
				etc_split[source] = coverage

		tmp_test = per_test_data
		tmp_test['test'] = test_name + '-c'
		tmp_test['source_files'] = c_split
		split_data.append(copy.deepcopy(tmp_test))

		tmp_test = per_test_data
		tmp_test['test'] = test_name + '-js'
		tmp_test['source_files'] = js_split
		split_data.append(copy.deepcopy(tmp_test))

		tmp_test = per_test_data
		tmp_test['test'] = test_name + '-etc'
		tmp_test['source_files'] = js_split
		split_data.append(copy.deepcopy(tmp_test))

	return split_data

