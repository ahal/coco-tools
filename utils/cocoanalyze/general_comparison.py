
def get_sets_common_and_different(files1, files2, forward_diff_name='list1-list2',
								 backward_diff_name='list2-list1', merge_diffs=False):
	different = {}
	common = list(files1 & files2)

	if not merge_diffs:
		different[forward_diff_name] = list(files1-files2)
		different[backward_diff_name] = list(files2-files1)
	else:
		different = list(files1 ^ files2)

	return (common, different)


def compare_coverage_files(file1, file2, level='file', file1_name='file1', file2_name='file2', merge_line_diffs=False):
	# Compare coverage between files. Returns a tuple in the form
	# (common, differences) where common is everything that is common
	# between the files, and differences contains anything different
	# between the two (we do a forward and backwards diff).
	file1_files = {el for el in file1}
	file2_files = {el for el in file2}

	forward_diff_name = file1_name + '-' + file2_name
	backward_diff_name = file2_name + '-' + file1_name

	common_files, different_files = get_sets_common_and_different(
		file1_files, file2_files,
		forward_diff_name=forward_diff_name,
		backward_diff_name=backward_diff_name
	)
	#import time
	#time.sleep(60)

	# Stop here if we only want file level differences.
	if level == 'file':
		return (list(common_files), different_files)

	line_level_common = {}
	line_level_different = {}
	for file in common_files:
		file1_lines = file1[file]
		file2_lines = file2[file]

		common_lines, different_lines = get_sets_common_and_different(
			set(file1_lines), set(file2_lines),
			forward_diff_name=forward_diff_name,
			backward_diff_name=backward_diff_name,
			merge_diffs=merge_line_diffs
		)

		line_level_common[file] = common_lines
		line_level_different[file] = different_lines

	# Add file level differences in.
	for file in different_files[forward_diff_name]:
		line_level_different[file] = {}
		line_level_different[file][forward_diff_name] = file1[file]

	for file in different_files[backward_diff_name]:
		line_level_different[file] = {}
		line_level_different[file][backward_diff_name] = file2[file]

	return (line_level_common, line_level_different)


def correct_ccov_for_baseline(ccov_data, baseline_ccov_data, level='file'):
	# Expects data strucutres like what is returned by jsonify_ccov_artifact(...).

	# Get level differences and common
	# The forward diff (ccov_data-baseline_ccov_data) is
	# what we are after.
	file1_name = 'ccov'
	file2_name = 'base'
	forward_diff_name = file1_name + '-' + file2_name
	_, different = compare_coverage_files(
		ccov_data, baseline_ccov_data, level=level,
		file1_name=file1_name, file2_name=file2_name
	)

	unique_to_data = different[forward_diff_name]
	return unique_to_data


def get_common_and_different(fmt_coverage1, fmt_coverage2, cov1_fname='jsdcov', cov2_fname='jsvm',
							 merge_line_diffs=False, level='file'):
	common_to_both = {}
	different_between = {}
	for count1, artifact1 in enumerate(fmt_coverage1):
		for count2, artifact2 in enumerate(fmt_coverage2):
			common, different = compare_coverage_files(
				artifact1, artifact2,
				level=level, file1_name=cov1_fname,
				file2_name=cov2_fname, merge_line_diffs=merge_line_diffs
			)

			curr_name = str(count1) + '-' + str(count2)
			common_to_both[curr_name] = common
			different_between[curr_name] = different

	return common_to_both, different_between


def format_per_test_list(json_data_list):
	new_list = []
	for per_test_data in json_data_list:
		new_list.append(per_test_data['source_files'])
	return new_list


def aggregate_reports(dest_report, src_report):
	# Restructure for easy access
	new_files = {}
	final_report = dest_report
	dest_files = dest_report['source_files']
	src_files = src_report['source_files']

	for file in src_files:
		cov_report = src_files[file]
		if file not in dest_files:
			new_files[file] = cov_report
			continue

		src_coverage = cov_report
		dst_coverage = dest_files[file]
		new_files[file] = list(set(src_coverage) | set(dst_coverage))

	for file in dest_files:
		if file in new_files:
			continue
		new_files[file] = dest_files[file]

	final_report['source_files'] = new_files
	return final_report


if __name__=="__main__":
	print("Not for use from CLI.")