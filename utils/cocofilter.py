import copy
from cocoload import pattern_find


def get_total_lines_hit_in_test(per_test_data, get_files=False):
	total_lines = 0
	for source in per_test_data['source_files']:
		coverage = per_test_data['source_files'][source]
		total_lines += len(coverage)
	return total_lines


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


def filter_per_test_lines(json_data_list, line_range):
	if not line_range:
		return json_data_list

	too_low = line_range[0]
	too_high = line_range[1]
	filtered_data_list = []
	for per_test_data in json_data_list:
		lines_hit = get_total_lines_hit_in_test(per_test_data)
		if too_low <= lines_hit <= too_high:
			per_test_data['lines_hit'] = lines_hit
			filtered_data_list.append(per_test_data)
	return filtered_data_list


def filter_per_test_all(json_data_list, test_matchers, source_matchers, line_range):
	filtered_tests = filter_per_test_tests(json_data_list, test_matchers)
	filtered_sources = filter_per_test_sources(filtered_tests, source_matchers)
	filtered_lines = filter_per_test_lines(filtered_sources, line_range)
	return filtered_lines


def filter_file_variability(json_data_list):
	good_sources = {}
	for count, per_test_data in enumerate(json_data_list):
		if count == 0:
			good_sources = per_test_data['source_files'].keys()
			continue
		good_sources = good_sources & per_test_data['source_files']
	
	filtered_data = filter_per_test_sources(json_data_list, list(good_sources))
	return filtered_data


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
		tmp_test['source_files'] = etc_split
		split_data.append(copy.deepcopy(tmp_test))

	return split_data


def group_tests(json_data_list):
	test_groups = {}
	for per_test_data1 in json_data_list:
		test_name = per_test_data1['test']
		if test_name in test_groups:
			continue

		test_groups[test_name] = []
		for per_test_data2 in json_data_list:
			if test_name == per_test_data2['test']:
				test_groups[test_name].append(per_test_data2)

	return test_groups
