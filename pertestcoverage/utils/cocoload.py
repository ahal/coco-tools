#!/usr/bin/python
# encoding=utf8


from __future__ import print_function, absolute_import

import os
import gzip
import json
import copy
import urllib.request
import logging

from . import timeout

RETRY = {"times": 3, "sleep": 5}
LEVEL_MAP = {
	'file': 1,
	'line': 2,
	'hits': 3
}

ACTIVE_DATA_URL = "http://54.149.21.8/query/"
HG_URL = "https://hg.mozilla.org/"

TYPE_PERTEST = "pertestreport"
TYPE_LCOV = "lcov"
TYPE_JSDCOV = "jsdcov"
TYPE_STDPTC = "std-ptc-format"

TYPE_FILE_WHITELIST = {
	TYPE_PERTEST: [".json"],
	TYPE_LCOV: [".info"],
	TYPE_JSDCOV: [".json"],
	TYPE_STDPTC: ["std-ptc-format.json"]
}

BRANCH_TO_HGBRANCH = {
	"mozilla-inbound": "integration/mozilla-inbound/",
    "autoland": "integration/autoland/",
    "mozilla-central": "mozilla-central/",
    "try": "try/"
}

log = logging.getLogger('pertestcoverage')


def pattern_find(srcf_to_find, sources):
	if sources is None:
		return True

	for srcf in sources:
		if srcf in srcf_to_find:
			return True
	return False


def hg_branch(branch):
	return BRANCH_TO_HGBRANCH[branch]


def file_in_type(file, filetype):
	for datatype in TYPE_FILE_WHITELIST[filetype]:
		if datatype in file:
			return True
	return False


def open_json(path, filename, fullpath=None):
	if fullpath == None:
		fullpath = os.path.join(path, filename)
	with open(fullpath, 'r') as f:
		data = json.load(f)
	return data


def save_json(data, path, filename):
	with open(os.path.join(path, filename), 'w') as f:
		json.dump(data, f, indent=4)


def chrome_mapping_rewrite(srcfiles, chrome_map_path, chrome_map_name=None):
	try:
		if not chrome_map_name:
			chrome_map_path, chrome_map_name = os.path.split(chrome_map_path)

		try:
			with open(os.path.join(chrome_map_path, chrome_map_name), 'r', encoding='utf-8') as f:
				chrome_mapping = json.load(f)[0]
		except:
			f = gzip.open(os.path.join(chrome_map_path, chrome_map_name), 'rb')
			data = f.read()
			chrome_mapping = json.loads(data)[0]
			f.close()

		new_srcfiles = {}
		for srcfile in srcfiles:
			new_name = srcfile
			if srcfile in chrome_mapping:
				new_name = chrome_mapping[srcfile]
			new_srcfiles[new_name] = srcfiles[srcfile]
	except Exception as e:
		log.info('Chrome mapping failed.')
		log.info('Exception: %s' % str(e))
		return srcfiles

	return new_srcfiles


def get_and_check_config(args=None, config=None):
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")
	return config


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


def get_coverage_tests(
		rev_n_branch_list=[],
		get_failed=False,
		get_files=[]
	):

	all_test_query_json = {
		"from":"coverage",
		"where":{"and":[
			{"eq":{"repo.changeset.id12":None}},
			{"eq":{"repo.branch.name":None}}
		]},
		"limit":100000,
		"groupby":[{"name":"test","value":"test.name"}]
	}

	if get_failed:
		all_test_query_json['where']['and'].append(
			{"ne":{"task.state":"completed"}}
		)

	if get_files:
		all_test_query_json['where']['and'].extend([
			{"in": {"source.file.name": get_files}},
			{"gt":{"source.file.total_covered":0}}
		])

	all_tests = []
	for rev, branch in rev_n_branch_list:
		all_test_query_json['where']['and'][0]['eq']['repo.changeset.id12'] = rev
		all_test_query_json['where']['and'][1]['eq']['repo.branch.name'] = branch

		try:
			all_tests = list(
				set(all_tests) | set(
					[testchunk[0] for testchunk in query_activedata(all_test_query_json)]
				)
			)
		except Exception as e:
			log.info("Failed to query for covered tests:" + str(e))

	return all_tests


def get_coverage_tests_from_jsondatalist(jsondatalist, get_files=['all']):
	all_tests = []
	for pertestjson in jsondatalist:
		if 'test' not in pertestjson:
			log.info("Cannot find test name in pertest json data.")
			continue

		if 'all' not in get_files:
			source_files = pertestjson['source_files']
			for file in get_files:
				if file in source_files:
					all_tests.append(pertestjson['test'])
					break
		else:
			all_tests.append(pertestjson['test'])
	return all_tests


def get_paths_from_dir(source_dir, file_matchers=None, filetype=TYPE_PERTEST):
	paths = []
	for root, _, files in os.walk(source_dir):
		for file in files:
			if not file_in_type(file, filetype):
				continue
			if pattern_find(file, file_matchers):
				paths.append((root, file))
	return paths


def get_jsonpaths_from_dir(jsons_dir, file_matchers=None):
	json_paths = get_paths_from_dir(jsons_dir, file_matchers=file_matchers)
	return json_paths


def get_lcovpaths_from_dir(lcov_dir, file_matchers=None):
	lcov_paths = get_paths_from_dir(lcov_dir, file_matchers=file_matchers, filetype=TYPE_LCOV)
	return lcov_paths


def get_stdptcpaths_from_dir(stdptc_dir, file_matchers=None):
	stdptc_paths = get_paths_from_dir(stdptc_dir, file_matchers=file_matchers, filetype=TYPE_STDPTC)
	return stdptc_paths


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


def get_all_pertest_data(pertestdir='', chrome_map_path=''):
	jsonpaths = get_jsonpaths_from_dir(pertestdir)
	json_data = []

	for root, file in jsonpaths:
		try:
			fmtd_test_dict = get_per_test_file(
				root, file, return_test_name=True
			)
			if chrome_map_path:
				fmtd_test_dict['source_files'] = chrome_mapping_rewrite(
					fmtd_test_dict['source_files'],
					chrome_map_path=chrome_map_path,
				)
			fmtd_test_dict['location'] = os.path.join(root, file)
			json_data.append(fmtd_test_dict)
		except Exception as e:
			log.info("Bad JSON found: " + str(os.path.join(root,file)))
			log.info("Exception: %s" % str(e))
			continue
	return json_data


def get_all_lcov_data(lcovdir='', chrome_map_path=''):
	lcovpaths = get_lcovpaths_from_dir(lcovdir)
	json_data = []

	for root, file in lcovpaths:
		try:
			fmtd_test_dict = get_jsvm_file(root, file)
			if chrome_map_path:
				fmtd_test_dict['source_files'] = chrome_mapping_rewrite(
					fmtd_test_dict['source_files'],
					chrome_map_path=chrome_map_path,
				)
			fmtd_test_dict['location'] = os.path.join(root, file)
			json_data.append(fmtd_test_dict)
		except Exception as e:
			log.info("Unknown error encountered while opening LCOV files: " + str(e))
	return json_data


def get_all_stdptc_data(stdptcdir='', chrome_map_path=''):
	paths = get_stdptcpaths_from_dir(stdptcdir)
	json_data = []

	for root, file in paths:
		try:
			fmtd_test_dict = get_std_ptc_file(root, file)
			if chrome_map_path:
				fmtd_test_dict['source_files'] = chrome_mapping_rewrite(
					fmtd_test_dict['source_files'],
					chrome_map_path=chrome_map_path,
				)
			fmtd_test_dict['location'] = os.path.join(root, file)
			json_data.append(fmtd_test_dict)
		except Exception as e:
			log.info("Unknown error encountered while opening LCOV files: " + str(e))
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
	with open(os.path.join(path, filename), 'r') as f:
		data = json.load(f)
	if type(data) != dict:
		raise KeyError("Not a dictionary JSON.")

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
		tmp = {
			'test': data['test'],
			'suite': data['suite'],
			'source_files': fmtd_per_test_data
		}
		return tmp
	return fmtd_per_test_data


def get_jsdcov_file(path, filename, get_test_url=False):
	data = open_json(path, filename)
	return format_jsdcov_file(data, get_test_url=get_test_url)


def format_jsdcov_file(jsdcov_data, get_test_url=False):
	fmtd_jsdcov_data = {}

	if get_test_url:
		fmtd_jsdcov_data = {
			'test': '',
			'source_files': {}
		}

	test_url = ''
	for cov_el in jsdcov_data:
		if 'sourceFile' not in cov_el:
			continue
		if get_test_url and not fmtd_jsdcov_data['test'] and 'testUrl' in cov_el:
			fmtd_jsdcov_data['test'] = cov_el['testUrl']

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


def rununtiltimeout(func):
	retries = 0
	response = None

	while retries < RETRY['times']:
		try:
			response = func()
			break
		except:
			if retries < RETRY['times']:
				retries += 1
				continue
			else:
				raise

	return response


def get_http_json(url):
	data = None

	@timeout(120)
	def get_data():
		with urllib.request.urlopen(url) as urllib_url:
			data = json.loads(urllib_url.read().decode())
		return data

	data = rununtiltimeout(get_data)
	return data


def query_activedata(query_json, debug=False, active_data_url=None):
	if not active_data_url:
		active_data_url = "http://activedata.allizom.org/query"

	@timeout(120)
	def get_data():
		req = urllib.request.Request(active_data_url)
		req.add_header('Content-Type', 'application/json')
		jsondata = json.dumps(query_json)

		jsondataasbytes = jsondata.encode('utf-8')
		req.add_header('Content-Length', len(jsondataasbytes))

		log.debug("Querying Active-data with: " + str(query_json))
		response = urllib.request.urlopen(req, jsondataasbytes)
		log.debug("Status:" + str(response.getcode()))
		return response

	response = rununtiltimeout(get_data)

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


def get_std_ptc_file(path, filename):
	return open_json(path, filename)


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
