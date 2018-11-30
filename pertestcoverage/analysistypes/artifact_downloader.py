import argparse
import json
import os
import zipfile
import shutil
import logging

from ..cli import AnalysisParser
from ..utils.cocoload import pattern_find
from ..utils import timeout

try:
	from urllib.parse import urlencode
	from urllib.request import urlopen, urlretrieve
except ImportError:
	from urllib import urlencode, urlretrieve
	from urllib2 import urlopen

log = logging.getLogger('pertestcoverage')

MAXRETRY = 10
URLRETRIEVE_TIMEOUT = 120

# Use this program to dowwnload, extract, and distribute GRCOV
# files that are to be used for the variability analysis.

# Use just the groupID, it absoutely needs to be given. With that, get the task details
# for the entire group, and find all the tests specified with the suite, chunk, and mode
# given through the parser arguments. For each of those tests, take the taskId
# and download the GRCOV data chunk. Continue suffixing them, however, store
# a json for a mapping from numbers to taskID's for future reference.

# The suite should include the flavor. It makes no sense to aggregate the data from
# multiple flavors together because they don't run the same tests. This is also
# why you cannot specify more than one suite and chunk.

def artifact_downloader_parser():
	parser = argparse.ArgumentParser("This tool can download the GRCOV data from a group of linux64-ccov " +
									 "taskcluster tasks. It then extracts the data, suffixes it with " +
									 "a number and then stores it in an output directory.")
	parser.add_argument('--task-group-id', type=str, nargs=1,
						help='The group of tasks that should be parsed to find all the necessary ' +
						'data to be used in this analysis. ')
	parser.add_argument('--test-suites-list', type=str, nargs='+',
						help='The listt of tests to look at. e.g. mochitest-browser-chrome-e10s-2.' +
						' If it`s empty we assume that it means nothing, if `all` is given all suites' +
						' will be processed.')
	parser.add_argument('--artifact-to-get', type=str, nargs=1, default='grcov',
						help='Pattern matcher for the artifact you want to download. By default, it' +
						' is set to `grcov` to get ccov artifacts. Use `per_test_coverage` to get data' +
						' from test-coverage tasks.')
	parser.add_argument('--unzip-artifact', action="store_true", default=False,
						help='Set to False if you don`t want the artifact to be extracted.')
	parser.add_argument('--output', type=str, nargs=1,
						help='This is the directory where all the download, extracted, and suffixed ' +
						'data will reside.')
	return parser


# Marco's functions, very useful.
def get_json(url, params=None):
	if params is not None:
		url += '?' + urlencode(params)
	r = urlopen(url).read().decode('utf-8')
	return json.loads(r)


def get_task_details(task_id):
	task_details = get_json('https://queue.taskcluster.net/v1/task/' + task_id)
	return task_details


def get_task_artifacts(task_id):
	artifacts = get_json('https://queue.taskcluster.net/v1/task/' + task_id + '/artifacts')
	return artifacts['artifacts']


def get_tasks_in_group(group_id):
	reply = get_json('https://queue.taskcluster.net/v1/task-group/' + group_id + '/list', {
		'limit': '200',
	})
	tasks = reply['tasks']
	while 'continuationToken' in reply:
		reply = get_json('https://queue.taskcluster.net/v1/task-group/' + group_id + '/list', {
			'limit': '200',
			'continuationToken': reply['continuationToken'],
		})
		tasks += reply['tasks']
	return tasks



def download_artifact(task_id, artifact, output_dir):
	fname = os.path.join(output_dir, task_id + '_' + os.path.basename(artifact['name']))
	log.info('Downloading ' + artifact['name'] + ' to: ' + fname)

	@timeout(URLRETRIEVE_TIMEOUT)
	def get_data():
		data = urlretrieve('https://queue.taskcluster.net/v1/task/' + task_id + '/artifacts/' + artifact['name'], fname)
		return data

	retries = 0
	while retries < MAXRETRY:
		try:
			data = get_data()
			break
		except:
			if retries < MAXRETRY:
				log.info("Retrying...")
				retries += 1
				continue
			else:
				raise

	return fname
# Marco's functions end #


def suite_name_from_task_name(name):
	namesplit = name.split('/')
	suite_name = namesplit[-1].strip('debug-').strip('opt-')
	return suite_name


def make_count_dir(a_path):
	if not os.path.exists(a_path):
		os.mkdir(a_path)
	return a_path


def unzip_file(abs_zip_path, output_dir, count=0):
	tmp_path = ''
	with zipfile.ZipFile(abs_zip_path, "r") as z:
		tmp_path = os.path.join(output_dir, str(count))
		make_count_dir(tmp_path)
		z.extractall(tmp_path)
	return tmp_path


def move_file(abs_filepath, output_dir, count=0):
	tmp_path = os.path.join(output_dir, str(count))
	make_count_dir(tmp_path)
	filename = abs_filepath.split('/')[-1]

	shutil.copyfile(abs_filepath, os.path.join(tmp_path, filename))
	return tmp_path


def artifact_downloader(
		task_group_id,
		output_dir=os.getcwd(),
		test_suites=[],
		download_failures=False,
		artifact_to_get='grcov',
		unzip_artifact=True,
		pattern_match_suites=False,
		use_task_name=True,
		task_id=''
	):

	head_rev = ''
	all_tasks = False
	if 'all' in test_suites:
		all_tasks = True

	task_ids = []
	if task_id:
		task_group_id = str(get_task_details(task_id)['taskGroupId'])

	tasks = get_tasks_in_group(task_group_id)

	# Make the data directories
	task_dir = os.path.join(output_dir, task_group_id)
	run_number = 0
	if not os.path.exists(task_dir):
		os.mkdir(task_dir)
	else:
		# Get current run number
		curr_dir = os.getcwd()
		os.chdir(task_dir)
		dir_list = next(os.walk('.'))[1]
		max_num = 0
		for subdir in dir_list:
			run_num = int(subdir)
			if run_num > max_num:
				max_num = run_num
		run_number = max_num + 1
		os.chdir(curr_dir)

	output_dir = os.path.join(output_dir, task_dir, str(run_number))
	os.mkdir(output_dir)

	# Used to keep track of how many grcov files 
	# we are downloading per test.
	task_counters = {}
	taskid_to_file_map = {}

	# For each task in this group
	for task in tasks:
		download_this_task = False
		# Get the test name
		test_name = task['task']['metadata']['name']
		if not use_task_name:
			test_name = suite_name_from_task_name(task['task']['metadata']['name'])

		# If all tests weren't asked for but this test is
		# asked for, set the flag.
		if (not all_tasks) and \
		   (test_name in test_suites or (pattern_match_suites and pattern_find(test_name, test_suites))):
			download_this_task = True

		test_name = test_name.replace('/', '-')
		if all_tasks or download_this_task:
			# Make directories for this task
			head_rev = task['task']['payload']['env']['GECKO_HEAD_REV']
			grcov_dir = os.path.join(output_dir, test_name)
			downloads_dir = os.path.join(os.path.join(grcov_dir, 'downloads'))
			data_dir = os.path.join(os.path.join(grcov_dir, (artifact_to_get.replace(".", "")) + '_data'))

			if test_name not in task_counters:
				os.mkdir(grcov_dir)
				os.mkdir(downloads_dir)
				os.mkdir(data_dir)
				task_counters[test_name] = 0
			else:
				task_counters[test_name] += 1
			task_id = task['status']['taskId']
			artifacts = get_task_artifacts(task_id)

			if not download_failures:
				failed = None
				for artifact in artifacts:
					if 'log_error' in artifact['name']:
						filen = download_artifact(task_id, artifact, downloads_dir)
						if os.stat(filen).st_size != 0:
							failed = artifact['name']
				if failed is not None:
					log.info('Skipping a failed test: ' + failed)
					continue

			for artifact in artifacts:
				if artifact_to_get in artifact['name']:
					log.info('\nOn artifact (%s):' % str(sum([v+1 for k,v in task_counters.items()])))
					fpath = download_artifact(task_id, artifact, downloads_dir)
					if artifact_to_get == 'grcov' or unzip_artifact:
						try:
							unzip_file(fpath, data_dir, task_counters[test_name])
						except:
							log.info("Could not unzip file. Moving it instead.")
							move_file(fpath, data_dir, task_counters[test_name])
					else:
						move_file(fpath, data_dir, task_counters[test_name])
					taskid_to_file_map[task_id] = os.path.join(
						data_dir, str(task_counters[test_name])
					)

	with open(os.path.join(output_dir, 'taskid_to_file_map.json'), 'w') as f:
		json.dump(taskid_to_file_map, f, indent=4)

	# Return the directory where all the tasks were downloaded to
	# and split into folders.
	return output_dir, head_rev

def run(args=None, config=None):
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")

	task_group_id = config['task_group_id'] if 'task_group_id' in config else None
	task_id = config['task_id'] if 'task_id' in config else None
	test_suites = config['test_suites_list']
	artifact_to_get = config['artifact_to_get']
	unzip_artifact = config['unzip_artifact']
	pattern_match_suites = config['pattern_match_suites']
	use_task_name = config['use_task_name'] if 'use_task_name' in config else True
	download_failures = config['download_failures'] if config['download_failures'] is not None else False
	outputdir = config['outputdir'] if config['outputdir'] is not None else os.getcwd()

	if 'timeout' in config:
		URLRETRIEVE_TIMEOUT = config['timeout']

	normed_outputdir = os.path.normpath(outputdir)
	if not os.path.isdir(normed_outputdir):
		log.info("outputdir is not a directory.")
		return None

	task_dir, head_rev = artifact_downloader(
		task_group_id, output_dir=normed_outputdir, test_suites=test_suites,
		artifact_to_get=artifact_to_get, unzip_artifact=unzip_artifact,
		pattern_match_suites=pattern_match_suites, download_failures=download_failures,
		use_task_name=use_task_name, task_id=task_id
	)

	return task_dir

if __name__ == '__main__':
	parser = artifact_downloader_parser()
	args = parser.parse_args()
	run(args=args)