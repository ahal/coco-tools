import copy
import os
import time
import logging

from ..cli import AnalysisParser
from ..utils.cocoanalyze.categorize import categorize_data, visualize_category_data
from ..utils.cocoload import (
	open_json,
	save_json,
	get_paths_from_dir
)

log = logging.getLogger('pertestcoverage')


def run(args=None, config=None):
	'''
		This program will parse *_per_changeset_breakdown.json
		type files from a given folder and search for cases where
		tests were not run and categorize them.

		categories:
			- 'c-changes'
			- 'unrelated-changes'
			- 'js-changes'
			- 'test-changes'
			- ...

		dirs:
			- /home/User/Documents/tmp/data1/
			- Downloads/
			- ...

		# If one of these match, the file is chosen
		file_matchers:
			- '_per_changeset_breakdown'
			- 'allsuites.json'

		# This path can be Null
		mozcentral-path: /home/Username/mozilla-source/mozilla-central/

	'''
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")

	all_dirs = config['dirs']
	categories = config['categories']
	file_matchers = config['file_matchers']

	file_paths = []
	for srcdir in all_dirs:
		file_paths.extend(
			get_paths_from_dir(srcdir, file_matchers=file_matchers)
		)

	data = []
	for path in file_paths:
		data.append(open_json(path[0], path[1]))

	categ_data = []
	for category in categories:
		categ_data.append({
			'category': category,
			'data': categorize_data(copy.deepcopy(data), category, **config)
		})

	categ_data.append({
		'category': 'all',
		'data': data
	})

	visualize_category_data(categ_data, **config)

	if 'outputdir' in config:
		save_json(
			categ_data,
			config['outputdir'],
			str(int(time.time())) + '_categ_data.json'
		)
