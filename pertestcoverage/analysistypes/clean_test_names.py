import os
import time
import logging

from ..cli import AnalysisParser
from ..utils.cocoload import save_json
from ..utils.cocofilter import clean_test_names

log = logging.getLogger('pertestcoverage')


def get_test_names_from_file(file, get_position=None):
	test_names = []
	flines = []

	with open(os.path.abspath(file), 'r') as f:
		flines = f.readlines()

	for line in flines:
		line = line.replace('\n', '')
		check_commas = line.split(',')
		if len(check_commas) > 1:
			if not get_position:
				log.warning('CSV file was given but no position to get was specified.')
				raise Exception(
					'PTC: Unknown file given for test names. '
					'Expecting one test name per line.'
				)
			elif get_position > len(check_commas)-1:
				raise Exception(
					'PTC: get_position is too high for '
					'size of CSV list, get_position=%s, len=%s' %
					(str(get_position), str(len(check_commas)))
				)

			line = check_commas[int(get_position)]

		test_names.append(line)
	return test_names


def run(args=None, config=None):
	'''
		Given a list of files in a YAML config with the
		following structure:

		Optional(
			# Perform the name change even if
			# the path doesn't exist.
			ignore_wpt_existence: True
			# Use for CSV files
			get-csv-position: 0
			test-files: [
				'file1',
				'file2',
				...
			]
		)

		# This path can be Null
		mozcentral-path: /home/Username/mozilla-source/mozilla-central/
		test-names: [
			't1',
			't2',
			...
		]

		This program will attempt to clean the test names
		to something usable.
	'''
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")

	mozcentral_path = None
	ignore_wpt_existence = False if 'ignore-wpt-existence' not in config else \
						   config['ignore-wpt-existence']
	if not ignore_wpt_existence:
		mozcentral_path = config['mozcentral-path'] if 'mozcentral-path' in config else \
						  None

	test_names = []
	if 'test-names' in config:
		test_names = config['test-names']
	if 'test-files' in config:
		for file in config['test-files']:
			try:
				get_position = None
				if 'get-csv-position' in config:
					get_position = config['get-csv-position']
				test_names += get_test_names_from_file(file, get_position=get_position)
			except Exception as e:
				if 'PTC:' in str(e):
					log.warning(
						'Error occurred for %s, continuing to next one: %s' %
						(file, str(e))
					)
				else:
					raise

	cleaned_test_names, mapping = clean_test_names(
		test_names,
		mozcentral_path=mozcentral_path,
		ignore_wpt_existence=ignore_wpt_existence
	)

	log.info('Cleaned test names: %s' % str(cleaned_test_names))
	log.info('\nMapping (old -> new):')
	for entry in mapping:
		log.info('\n%s -> %s\n' % (entry, mapping[entry]))

	if 'outputdir' in config:
		save_json(
			mapping,
			config['outputdir'],
			str(int(time.time())) + '_map_of_old_to_new_names.json'
		)
