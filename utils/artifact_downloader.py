import argparse
import json
import os
import zipfile
import shutil

try:
	from urllib.parse import urlencode
	from urllib.request import urlopen, urlretrieve
except ImportError:
	from urllib import urlencode, urlretrieve
	from urllib2 import urlopen

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
	print('Downloading ' + artifact['name'] + ' to: ' + fname)
	urlretrieve('https://queue.taskcluster.net/v1/task/' + task_id + '/artifacts/' + artifact['name'], fname)
	return fname


def suite_name_from_task_name(name):
	name = name[len('test-linux64-ccov/opt-'):]
	return name
# Marco's functions end #


def unzip_grcov(abs_zip_path, output_dir, count=0):
	tmp_path = ''
	with zipfile.ZipFile(abs_zip_path, "r") as z:
		tmp_path = os.path.join(output_dir, str(count))

		def make_count_dir(a_path):
			os.mkdir(a_path)
			return a_path
		z.extractall(tmp_path if os.path.exists(tmp_path)\
							  else make_count_dir(tmp_path))

	grcov_file_path = ''
	new_file_path = ''
	for dirpath, dirnames, filenames in os.walk(tmp_path):
		for filename in filenames:
			grcov_file_path = os.path.join(dirpath, filename)
			new_file_path = os.path.join(output_dir, 'grcov_lcov_output_stdout' + str(count) + '.info')

	shutil.copyfile(grcov_file_path, new_file_path)

def artifact_downloader(task_group_id, output_dir=os.getcwd(), test_suites=[], download_failures=False):
	head_rev = ''
	all_tasks = False
	if 'all' in test_suites:
		all_tasks = True

	task_ids = []
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

	# For each task in this group
	for task in tasks:
		download_this_task = False
		# Get the test name
		if not task['task']['metadata']['name'].startswith('test-linux64-ccov'):
			continue
		test_name = suite_name_from_task_name(task['task']['metadata']['name'])

		# If all tests weren't asked for but this test is
		# asked for, set the flag.
		if (not all_tasks) and test_name in test_suites:
			download_this_task = True

		if all_tasks or download_this_task:
			# Make directories for this task
			head_rev = task['task']['payload']['env']['GECKO_HEAD_REV']
			grcov_dir = os.path.join(output_dir, test_name)
			downloads_dir = os.path.join(os.path.join(grcov_dir, 'downloads'))
			data_dir = os.path.join(os.path.join(grcov_dir, 'grcov_data'))

			if test_name not in task_counters:
				os.mkdir(grcov_dir)
				os.mkdir(downloads_dir)
				os.mkdir(data_dir)
				task_counters[test_name] = 0
			else:
				task_counters[test_name] += 1
			task_id = task['status']['taskId']
			artifacts = get_task_artifacts(task_id)

			failed = None
			for artifact in artifacts:
				if 'log_error' in artifact['name']:
					filen = download_artifact(task_id, artifact, downloads_dir)
					if os.stat(filen).st_size != 0:
						failed = artifact['name']
			if (failed is not None) and (not download_failures):
				print('Skipping a failed test: ' + failed)
				continue

			for artifact in artifacts:
				if 'grcov' in artifact['name']:
					filen = download_artifact(task_id, artifact, downloads_dir)
					unzip_grcov(filen, data_dir, task_counters[test_name])
					break
	print('done')
	# Return the directory where all the tasks were downloaded to
	# and split into folders.
	return output_dir, head_rev

def main():
	parser = artifact_downloader_parser()
	args = parser.parse_args()

	task_group_id = args.task_group_id[0]
	test_suites = args.test_suites_list
	output_dir = args.output[0] if args.output is not None else os.getcwd()

	task_dir, head_rev = artifact_downloader(task_group_id, output_dir=output_dir, test_suites=test_suites)

	return task_dir

if __name__ == '__main__':
	main()