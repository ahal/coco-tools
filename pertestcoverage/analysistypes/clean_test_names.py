import os
import time
import logging
import json

from ..cli import AnalysisParser
from ..utils.cocoload import save_json
from ..utils.cocofilter import clean_test_names

log = logging.getLogger('pertestcoverage')

CLEAN_TYPES = [
	'mochitest',
	'wpt'
]


def get_lines(file):
	with open(os.path.abspath(file), 'r') as f:
		flines = f.readlines()
	return flines

def get_test_names_from_file(file, get_position=None):
	test_names = []
	flines = get_lines(file)

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


def get_suites(file, numsuites=0):
	flines = get_lines(file)
	numsuites = len(flines)

	try:
		suites = []

		for line in flines:
			suites.append(line.replace('\n', '').split(',')[1])

		return suites
	except Exception as e:
		log.info('Could not get suites. Error: %s' % str(e))

		return ['' for _ in range(numsuites)]


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

	mozcentral_path = config['mozcentral-path'] if 'mozcentral-path' in config else \
					  None
	ignore_wpt_existence = False if 'ignore-wpt-existence' not in config else \
						   config['ignore-wpt-existence']

	clean_type = 'wpt' if 'clean-type' not in config and \
					   config['clean-type'] not in CLEAN_TYPES else \
				 config['clean-type']

	test_names = []
	suites = []
	if 'test-names' in config:
		test_names = config['test-names']
	if 'test-files' in config:
		for file in config['test-files']:
			try:
				get_position = None
				if 'get-csv-position' in config:
					get_position = config['get-csv-position']
				test_names += get_test_names_from_file(file, get_position=get_position)
				suites += get_suites(file)
			except Exception as e:
				if 'PTC:' in str(e):
					log.warning(
						'Error occurred for %s, continuing to next one: %s' %
						(file, str(e))
					)
				else:
					raise

	cleaned_test_names = []
	mapping = {}
	if clean_type in ('mixed', 'wpt'):
		cleaned_test_names, mapping = clean_test_names(
			test_names,
			mozcentral_path=mozcentral_path,
			ignore_wpt_existence=ignore_wpt_existence,
			suites=suites if clean_type in ('mixed',) else None
		)

		if clean_type == 'mixed':
			new_mapping = {}
			for oldtest, newtest in mapping.items():
				new_mapping[oldtest] = newtest.split('ini:')[-1]
			cleaned_test_names = new_mapping.values()
			mapping = new_mapping
	else:
		# Not much to do for other suites,
		# just need to remove .ini prefixes.
		for test in test_names:
			mapping[test] = test.split('ini:')[-1]
		cleaned_test_names = mapping.values()

	if 'show_output' in config and config['show_output']:
		log.info('\nMapping (old -> new):')
		for entry in mapping:
			log.info('\n%s -> %s\n' % (entry, mapping[entry]))

	log.info('Finished cleaning')
	log.info('Total left: %s' % len(mapping.values()))
	if 'outputdir' in config and config['outputdir']:
		currtime = str(int(time.time()))
		fname = currtime + '_map_of_old_to_new_names.json'
		log.info('Saving results to %s in %s' % (fname, config['outputdir']))

		save_json(
			mapping,
			config['outputdir'],
			fname
		)

		with open(
			os.path.join(config['outputdir'], fname.split('.')[0] + '.csv'),
			'w'
		) as f:
			f.write(
				'\n'.join([','.join([k,v]) for k,v in mapping.items()])
			)

		if 'outputteststoverify' in config:
			with open(os.path.join(config['outputdir'], 'tests_to_verify.json'), 'w+') as f:
				json.dump({'files': list(mapping.values())}, f, indent=4)
