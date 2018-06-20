import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cocoload import get_all_jsons
from cocofilter import filter_per_test_all, split_file_types


def check_args_and_get_data(args=None):
	# Args must be obtained from pertestcoverage_view.py parser.
	if args is None:
		return None

	json_data = get_all_jsons(args)
	filtered_json_data = filter_per_test_all(json_data, args.tests, args.sources)

	if args.split_types:
		filtered_json_data = split_file_types(filtered_json_data)

	return filtered_json_data


def differences_analysis(args=None, save=True, filt_and_split_data=None):
	# Plots total lines hit across all files (global variability),
	# the ratio (lines hit / number of files) for a more accurate comparison,
	# and an overlay of the number of lines hit in each file (in gray) with
	# a mean of those lines shown over top (in blue).

	if not filt_and_split_data:
		filt_and_split_data = check_args_and_get_data(args=args)
		if not filt_and_split_data:
			return None

	OUTPUT_DIR = args.output_dir
	level = 'file'
	if args.line_level:
		level = 'line'

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