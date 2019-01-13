import logging
import random

log = logging.getLogger('pertestcoverage')


class ExampleScheduler:
	def __init__(self, config={}):
		log.info("I see a config!")
		log.info(config)

	def analyze_fbc_entry(self, entry, fmt_testname):
		'''
			entry is a tuple of the following format:
			(changeset, suite, repo, test_fixed)
		'''
		changeset, suite, repo, test_fixed = entry

		result = {
			'success': False,
			'skip': False
		}

		log.info("Found the formatted test: {}".format(fmt_testname))

		val = random.random()
		if val < 0.3:
			log.info("You shall not pass, {}!".format(test_fixed))
			return result
		elif 0.3 <= val < 0.6:
			log.info("You've passed, {}!".format(test_fixed))
			result['success'] = True
			return result
		else:
			log.info("A mysterious force prevents {} from being considered!".format(test_fixed))
			result['skip'] = True
			return result