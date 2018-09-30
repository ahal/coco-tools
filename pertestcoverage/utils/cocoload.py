import os
import json
import copy
import urllib.request
import logging

RETRY = {"times": 3, "sleep": 5}
LEVEL_MAP = {
	'file': 1,
	'line': 2,
	'hits': 3
}

ACTIVE_DATA_URL = "http://54.149.21.8/query/"
HG_URL = "https://hg.mozilla.org/"

log = logging.getLogger('pertestcoverage')


def pattern_find(srcf_to_find, sources):
	if sources is None:
		return True

	for srcf in sources:
		if srcf in srcf_to_find:
			return True
	return False

def open_json(path, filename):
	with open(os.path.join(path, filename), 'r') as f:
		data = json.load(f)
	return data


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


def get_changesets(hg_analysisbranch, startrevision, numpatches):
	changesets = []
	currrev = startrevision

	while len(changesets) < numpatches:
		changelog_url = HG_URL + hg_analysisbranch + "/json-log/" + currrev

		data = get_http_json(changelog_url)
		clog_csets_list = list(data['changesets'])
		changesets.extend([el['node'][:12] for el in clog_csets_list[:-1]])

		currrev = clog_csets_list[-1]['node'][:12]

	changesets = changesets[:numpatches]
	return changesets


def get_jsonpaths_from_dir(jsons_dir, file_matchers=None):
	json_paths = []
	for root, _, files in os.walk(jsons_dir):
		for file in files:
			if '.json' not in file:
				continue
			if pattern_find(file, file_matchers):
				json_paths.append((root, file))
	return json_paths


def get_all_jsons(args=None):
	# These arguments come from a parser which is or uses the
	# pertestcoverage_view.py parser.
	if args is None:
		print("No arguments given.")
		return None

	# For opening the JSONs, taken from pertestcoverage_view.py's parser
	DATA_DIR = args.PER_TEST_DIR
	test_files = args.tests
	score_range = args.scores
	scored_file = args.scoredfile
	ignore_uniques = args.getuniques

	jsonpaths = get_jsonpaths_from_dir(DATA_DIR)
	json_data = []

	for root, file in jsonpaths:
		try:
			if scored_file:
				fmtd_test_dict = get_per_test_scored_file(
					root, file, return_test_name=True,
					score_range=score_range, ignore_uniques=ignore_uniques
				)
			else:
				fmtd_test_dict = get_per_test_file(
					root, file, return_test_name=True
				)
			fmtd_test_dict['location'] = os.path.join(root, file)
			json_data.append(fmtd_test_dict)
		except KeyError as e:
			print("Bad JSON found: " + str(os.path.join(root,file)))
	return json_data


def get_per_test_scored_file(path, filename, get_hits=False, 
							 return_test_name=False, score_range=None,
							 ignore_uniques=True, full_path=None
							 ):
	with open(os.path.join(path, filename)) as f:
		data = json.load(f)
	return format_per_test_scored_file(
		data, return_test_name=return_test_name, get_hits=get_hits, score_range=score_range
	)


def format_per_test_scored_file(data, return_test_name=False, get_hits=False,
								get_type='test', # Can be 'test' or 'baseline'
								score_range=None, # Returns lines unique to the test if none or in the range [low, high] (inclusive)
								ignore_uniques=True, # Ignores unique test lines
								):
	def check_for_hits(line, hits, get_hits=False):
		if get_hits:
			return (line, hits)
		return line

	fmtd_per_test_data = {}
	for cov in data['report']['source_files']:
		if 'name' not in cov or 'coverage' not in cov:
			continue

		broke = False
		broken_on = []
		new_coverage = []
		for count, cov_list in enumerate(cov['coverage']):
			if cov_list is None or type(cov_list) == int:
				broke = True
				broken_on.append(cov['name'])
				continue
			line_num = count + 1
			test_hit_count = cov_list[0]
			score = cov_list[1]

			if score_range is None:
				if get_type == 'test':
					if score is None and test_hit_count is not None and test_hit_count > 0 :
						new_coverage.append(check_for_hits(line_num, test_hit_count, get_hits=get_hits))
				elif get_type == 'baseline':
					if test_hit_count is not None and score is not None and score == -1:
						new_coverage.append(check_for_hits(line_num, test_hit_count, get_hits=get_hits))
				continue

			if test_hit_count is not None:
				if score is None:
					if get_type == 'test' and not ignore_uniques:
						new_coverage.append(check_for_hits(line_num, test_hit_count, get_hits=get_hits))
					continue
				if score_range[0] <= float(score) <= score_range[1]:
					new_coverage.append(check_for_hits(line_num, test_hit_count, get_hits=get_hits))

		if get_type == 'test':
			if len(new_coverage) == 0:
				continue
		fmtd_per_test_data[cov['name']] = new_coverage
	print("Broken on:" + "\n".join(broken_on))
	if return_test_name:
		return {
			'test': data['test'],
			'suite': data['suite'],
			'source_files': fmtd_per_test_data
		}
	return fmtd_per_test_data



def get_per_test_file(path, filename, get_hits=False, return_test_name=False):
	with open(os.path.join(path, filename)) as f:
		data = json.load(f)
	return format_per_test_file(
		data, return_test_name=return_test_name, get_hits=get_hits
	)



def format_per_test_file(data, get_hits=False, return_test_name=False):
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
	if return_test_name:
		return {
			'test': data['test'],
			'suite': data['suite'],
			'source_files': fmtd_per_test_data
		}
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


def get_http_json(url):
	data = None
	with urllib.request.urlopen(url) as urllib_url:
		data = json.loads(urllib_url.read().decode())
	return data


def query_activedata(query_json, debug=False, active_data_url=None):
	if not active_data_url:
		active_data_url = "http://54.149.21.8/query"

	req = urllib.request.Request(active_data_url)
	req.add_header('Content-Type', 'application/json')
	jsondata = json.dumps(query_json)

	jsondataasbytes = jsondata.encode('utf-8')
	req.add_header('Content-Length', len(jsondataasbytes))

	log.debug("Querying Active-data with: " + str(query_json))
	response = urllib.request.urlopen(req, jsondataasbytes)
	log.debug("Status:" + str(response.getcode()))

	data = json.loads(response.read().decode('utf8').replace("'", '"'))['data']
	return data


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


def format_to_level(json_data_list, level='line', curr_level=None):
	if not curr_level:
		prev_level = curr_level
		for per_test_data in json_data_list:
			curr_level = level_check(per_test_data)
			if not prev_level:
				prev_level = curr_level
			elif prev_level != curr_level:
				print(
					"Error, datasets are not at the same level, previous level was `" + str(prev_level) +
					"` and current level is `" + str(curr_level) + "`"
				)
				return json_data_list

	if LEVEL_MAP[curr_level] < LEVEL_MAP[level]:
		print(
			"Warning, requested level `" + str(level) + "` is above the "
			"current level, that is `" + str(curr_level) + "`"
		)
		return json_data_list
	elif LEVEL_MAP[curr_level] == LEVEL_MAP[level]:
		return json_data_list

	return lower_data_level(json_data_list, level=level)


def level_check(json_data):
	if type(json_data) == dict:
		if len(json_data) > 0:
			for entry in json_data:
				first_el = json_data[entry]
				break
			if type(first_el) == list and len(first_el) > 0:
				if type(first_el[0]) == tuple:
					return 'hits'
		return 'line'
	return 'file'


def lower_data_level(json_data_list, level):
	# Use format_to_level for a "guarantee" that
	# there will be no errors when moving levels.
	# It assumes the curr_level is known by user.
	new_data_list = []
	for per_test_data in json_data_list:
		new_test_data = []
		if level == 'file':
			new_test_data = list(per_test_data.keys())
		elif level == 'line':
			new_test_data = {}
			for sf in per_test_data:
				new_test_data[sf] = [line for line, _ in per_test_data[sf]]
		else:
			# Default to the same type
			new_test_data = per_test_data
		new_data_list.append(new_test_data)
	return new_data_list


if __name__=="__main__":
	print("Not for use from CLI.")
