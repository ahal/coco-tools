import os
import json
import copy
import urllib
from utils import artifact_downloader

RETRY = {"times": 3, "sleep": 5}


def save_json(data, path, filename):
	with open(os.path.join(path, filename), 'w') as f:
		json.dump(data, f, indent=4)


def chrome_mapping_rewrite(srcfiles, chrome_map_path, chrome_map_name):
	with open(os.path.join(chrome_map_path, chrome_map_name)) as f:
		chrome_mapping = json.load(f)[0]

	new_srcfiles = {}
	for srcfile in srcfiles:
		new_name = srcfile
		if srcfile in chrome_mapping:
			new_name = chrome_mapping[srcfile]
		new_srcfiles[new_name] = srcfiles[srcfile]

	return new_srcfiles


def get_per_test_file(path, filename):
	with open(os.path.join(path, filename)) as f:
		data = json.load(f)
	return format_per_test_file(data)


def format_per_test_file(data, get_hits=False):
	fmtd_per_test_data = {}
	for cov in data['report']['source_files']:
		if 'name' not in cov or 'coverage' not in cov:
			continue
		new_coverage = [
			count+1 if not get_hits else (count+1, i)
			for count, i in enumerate(cov['coverage']) \
				if i is not None and i > 0
		]

		fmtd_per_test_data[cov['name']] = new_coverage
	return fmtd_per_test_data


def get_jsdcov_file(path, filename):
	with open(os.path.join(path, filename)) as f:
		data = json.load(f)
	return format_jsdcov_file(data)


def format_jsdcov_file(jsdcov_data):
	fmtd_jsdcov_data = {}
	for cov_el in jsdcov_data:
		if 'sourceFile' not in cov_el:
			continue

		fmtd_jsdcov_data[cov_el['sourceFile']] = cov_el['covered']
	return fmtd_jsdcov_data


def get_ad_jsdcov_file(taskID):
	# We expect this task to have only one test
	# run in it, unless testURL is specified and that you
	# are sure there was no aggregation being performed
	# when active data ingested the data: 
	# https://github.com/klahnakoski/ActiveData-ETL/blob/e81c32246afb2
	# f26f63e9968a9c822c76065f326/activedata_etl/transforms/jsdcov_to_es.py#L24.
	query_json = {
		"from":"coverage",
		"where":{"eq":{"task.id":taskID}},
		"limit":1000,
		"select":[
			{"name":"source.file.name","value":"source.file.name"},
			{"name":"coverage","value":"source.file.covered"}
		]
	}
	return format_generic_activedata_coverage_response(
		query_activedata(query_json)
	)


def query_activedata(query_json):
	active_data_url = 'http://activedata.allizom.org/query'

	req = urllib.request.Request(active_data_url)
	req.add_header('Content-Type', 'application/json')
	jsondata = json.dumps(query_json)

	jsondataasbytes = jsondata.encode('utf-8')
	req.add_header('Content-Length', len(jsondataasbytes))

	print("Querying Active-data for task ID " + str(query_json['where']['eq']['task.id']) +
		  ": \n" + str(query_json))
	response = urllib.request.urlopen(req, jsondataasbytes)
	print("Status:" + str(response.getcode()))

	data = json.loads(response.read().decode('utf8').replace("'", '"'))['data']
	return [(i, data['coverage'][count]) for count, i in enumerate(data['source.file.name'])]


def format_generic_activedata_coverage_response(response):
	fmt_data = {}
	for entry in response:
		fmt_data[entry[0]] = [int(el) for el in list(entry[1])]
	return fmt_data


def load_artifact(file_path):
	try:
		lines = []
		with open(file_path, 'r') as f:
			lines = f.readlines()
		return lines
	except FileNotFoundError:
		return None


def get_jsvm_file(path, filename, jsonify=True):
	artifact_data = load_artifact(os.path.join(path, filename))
	if not jsonify:
		return artifact_data
	else:
		return jsonify_ccov_artifact(artifact_data)


def jsonify_ccov_artifact(file_lines):
	# Restructures raw artifact file to:
	# {'source_file_name': [covered lines]}
	current_sf = ''
	new_hit_lines = {}
	for i in range(0, len(file_lines)):
		if file_lines[i].startswith('SF'):
			# Set the current source file to gather lines for
			current_sf = file_lines[i]
		if file_lines[i].startswith('DA'):
			# Get the line number
			line, line_count = file_lines[i].replace('DA:', '').split(',')
			if int(line_count) > 0:
				if current_sf not in new_hit_lines:
					new_hit_lines[current_sf] = []
				new_hit_lines[current_sf].append(int(line))

	return format_sfnames(new_hit_lines)


def format_sfnames(differences):
	# Removes the SF: and new line from the source file names
	new_differences = {}
	for sf in differences:
		new_sf = sf.replace('SF:', '', 1)
		new_sf = new_sf.replace('\n', '')
		new_differences[new_sf] = differences[sf]
	return new_differences


def get_sets_common_and_different(files1, files2, forward_diff_name='list1-list2',
								 backward_diff_name='list2-list1', merge_diffs=False):
	different = {}
	common = list(files1 & files2)
	print(files1)
	print("\n\n\n\n")
	print(files2)

	print("\n\n\n\n")
	print("COMMON:")
	print(common)

	if not merge_diffs:
		different[forward_diff_name] = list(files1-files2)
		different[backward_diff_name] = list(files2-files1)
	else:
		different = list(files1 ^ files2)

	print("\n\n\n\n")
	print("DIFFERENT:")
	print(different)
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
	print(common_files)
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


def main():
	# Analysis 1, check similarities and differences. (No aggregation)
	level = 'line'
	merge_line_diffs = False
	DATA_DIR = """C:\\Users\\greg\\Documents\\mozwork\\New folder\\per-test-coverage-reports(62)"""

	baseline_file = "f0e2b06a-4208-42b8-a81d-9ec4dad1a595.json"
	test_file = "bc7043e7-051a-425c-9937-7766dcb98a7d.json"
	diffed_file = "bc7043e7-051a-425c-9937-7766dcb98a7d.json_diffed.json"

	fmtd_basef = get_per_test_file(DATA_DIR, baseline_file)
	fmtd_testf = get_per_test_file(DATA_DIR, test_file)
	fmtd_diff = get_per_test_file(DATA_DIR, diffed_file)

	for i in fmtd_testf:
		if i not in fmtd_diff:
			continue
		if i not in fmtd_basef:
			continue

		base_lines = fmtd_basef[i]
		test_lines = fmtd_testf[i]
		diff_lines = fmtd_diff[i]

		for line in diff_lines:
			if line in test_lines:
				if line in base_lines:
					print("Error - diff line shouldn't be here as it's in baseline. For " + i + " , Line: " + str(line))
			else:
				print("Error - diff line shouldn't be here as it's not in the test file. For " + i + " , Line: " + str(line))

		print("Source file: " + str(i) + "  is good with coverage after diffing: \n" + str(diff_lines))
		print("Baseline data: " + str(base_lines))
		print("Test data: " + str(test_lines))

	print("Finished testing.")


if __name__ == "__main__":
	main()