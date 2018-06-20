import os
import sys
import numpy as np
from matplotlib import pyplot as plt

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cocoload import get_all_jsons
from cocofilter import (
	filter_file_variability,
	filter_per_test_all,
	get_total_lines_hit_in_test,
	group_tests,
	split_file_types
)


def check_args_and_get_data(args=None):
	# Args must be obtained from pertestcoverage_view.py parser.
	if args is None:
		return None

	json_data = get_all_jsons(args)
	filtered_json_data = filter_per_test_all(json_data, args.tests, args.sources, args.line_range)

	if args.split_types:
		filtered_json_data = split_file_types(filtered_json_data)

	return filtered_json_data


def differences_analysis(args=None, save=True, filt_and_split_data=None):
	# Plots total lines hit across all files (global variability),
	# the ratio (lines hit - mean of lines hit) for a more accurate view,
	# and an overlay of the number of lines hit in each file (in gray) with
	# a mean of those lines shown over top (in blue) for 3 figures.

	if not filt_and_split_data:
		filt_and_split_data = check_args_and_get_data(args=args)
		if not filt_and_split_data:
			return None

	OUTPUT_DIR = args.output_dir
	level = 'file'
	if args.line_level:
		level = 'line'

	test_groups = group_tests(filt_and_split_data)
	for test in test_groups:
		# For each test, perform the plotting mentioned above.
		print("Running test: " + test)
		json_data = test_groups[test]

		## Plot all lines hit across all files (global) ##
		total_lines_per_test = []
		for per_test_data in json_data:
			if 'lines_hit' in per_test_data:
				total_lines_per_test.append(per_test_data['lines_hit'])
				continue
			total_lines = get_total_lines_hit_in_test(per_test_data)
			total_lines_per_test.append(total_lines)

		plt.figure()
		inds = np.arange(len(total_lines_per_test))
		plt.plot(inds, total_lines_per_test)
		plt.title("Total lines hit over time for: " + test)
		plt.ylabel("Lines Hit")
		plt.xlabel("Test Number")

		# Plot it recalculated as a change from mean
		mean = np.mean(total_lines_per_test)
		recalced = [(hits-mean) for hits in total_lines_per_test]
		plt.figure()
		plt.plot(inds, recalced)
		plt.title("Total lines hit relative to mean" + str(int(mean)) + ": " + test)
		plt.ylabel("Lines Hit")
		plt.xlabel("Test Number")

		## Plot overlay ##

		# Here we need to remove all file level variability
		json_data = filter_file_variability(json_data)

		print("Close all figures to see the next test...")
		plt.show()
		continue

	return filt_and_split_data


def aggregation_graph_analysis(args=None, save=True):
	filt_and_split_data = check_args_and_get_data(args=args)
	if not filt_and_split_data:
		return None

	OUTPUT_DIR = args.output_dir
	level = 'file'
	if args.line_level:
		level = 'line'

	return filt_and_split_data
