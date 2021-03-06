import os
import sys
import time
import copy
import numpy as np
import json
from matplotlib import pyplot as plt

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cocoload import get_all_jsons, save_json, format_to_level
from cocoanalyze.general_comparison import (
	aggregate_reports,
	format_per_test_list,
	get_common_and_different
)

from cocofilter import (
	filter_file_variability,
	filter_freqs,
	filter_per_test_sources,
	filter_per_test_all,
	filter_ttest,
	get_total_lines_hit_in_test,
	group_tests,
	split_file_types
)


def wrap_args(args):
	if type(args) == dict:
		args = wrap(args)
	return args


def check_args_and_get_data(args=None):
	if args is None:
		return None
	args = wrap_args(args)

	json_data = get_all_jsons(args)
	filtered_json_data = filter_per_test_all(json_data, args.tests, args.sources, args.line_range)

	if args.split_types:
		filtered_json_data = split_file_types(filtered_json_data)

	return filtered_json_data


def get_and_plot_differences(json_data, test='', plot_total_lines=True, args=None, show_stability=False):
	if args is None:
		return None
	args = wrap_args(args)

	variability_threshold = args.variability_threshold
	correlation_threshold = args.correlation_threshold

	# Here we need to remove all file level variability
	print("Removing file variability.")
	json_data = filter_file_variability(json_data)
	inds = np.arange(len(json_data))

	## Plot all lines hit across all files (global) ##
	if plot_total_lines:
		# Get global hit counts and plot them
		total_lines_per_test = []
		for per_test_data in json_data:
			# This might have been calculated in filter_per_test_lines
			if 'lines_hit' in per_test_data:
				total_lines_per_test.append(per_test_data['lines_hit'])
				continue
			total_lines = get_total_lines_hit_in_test(per_test_data)
			total_lines_per_test.append(total_lines)

		plt.figure()
		plt.plot(inds, total_lines_per_test)
		plt.title("Total lines hit over time for: " + test)
		plt.ylabel("Lines Hit")
		plt.xlabel("Test Number")

		# Plot it recalculated as a change from mean
		mean = np.mean(total_lines_per_test)
		recalced = [(hits-mean) for hits in total_lines_per_test]
		plt.figure()
		plt.plot(inds, recalced)
		plt.title("Total lines hit relative to the mean " + str(int(mean)) + ": " + test)
		plt.ylabel("Lines Hit")
		plt.xlabel("Test Number")

	## Plot overlay ##

	# Get hits per test per file
	source_files_to_plot = {}
	for i, per_test_data in enumerate(json_data):
		for source in per_test_data['source_files']:
			coverage = per_test_data['source_files'][source]
			if source not in source_files_to_plot:
				source_files_to_plot[source] = []
				for j in range(i):
					source_files_to_plot[source].append(0)
			source_files_to_plot[source].append(len(coverage))

		for source in source_files_to_plot:
			if len(source_files_to_plot[source]) != i+1:
				source_files_to_plot[source].append(0)


	# Variability filter the lines
	print("Running variability filter...")
	filt_sources_to_plot = {}
	for source in source_files_to_plot:
		hits = source_files_to_plot[source]

		keep_source = False
		prev_hit = hits[0]
		for hit in hits:
			if variability_threshold[0] <= abs(hit - prev_hit) <= variability_threshold[1]:
				keep_source = True
			prev_hit = hit
		if keep_source:
			filt_sources_to_plot[source] = hits

	plt.figure()
	all_lines = []
	for source in filt_sources_to_plot:
		hits = filt_sources_to_plot[source]
		hits = hits - np.mean(hits)
		if hits[0] < 0:
			# Flip the graph so differences
			# decrease
			hits = hits * -1
		plt.plot(inds, hits, color='grey')
		all_lines.append(hits)
	# Get mean hits
	mean_plot = np.mean(all_lines, 0)
	plt.plot(inds, mean_plot, color='darkblue')
	plt.ylabel("Lines changed")
	plt.xlabel("Test number ")
	title = "Change in file coverage overtime for all files found "
	if show_stability:
		max_linechange = max(mean_plot)
		min_linechange = min(mean_plot)
		stability_score = round(
			100 * (1/((max_linechange - min_linechange) + 1)),
			2
		)
		title += "Stability=" + str(stability_score) + "%"
	plt.title(title)

	if variability_threshold[0] <= 20 and len(filt_sources_to_plot) > 20:
		print("WARNING: This may take a while. Consider increasing " + 
			  "the variability-threshold.")

	# Normalize
	normed_data = {}
	for s in filt_sources_to_plot:
		coverage = filt_sources_to_plot[s]
		max_cov = max(coverage)
		min_cov = min(coverage)

		def inrange_constant(val):
			while val/10 > 1:
				val = val/10
			return val/10

		new_coverage = [
			(c-min_cov)/(max_cov-min_cov) if max_cov - min_cov != 0 else inrange_constant(c)
			for c in coverage
		]
		normed_data[s] = new_coverage

	# Compare
	data_to_save = {}
	for count, s1 in enumerate(normed_data):
		curr_cov = normed_data[s1]
		if max(curr_cov) - min(curr_cov) == 0:
			continue

		found_it = False
		for grouping in data_to_save:
			if s1 in data_to_save[grouping]['sources'].keys():
				found_it = True
		if found_it:
			continue

		similar_sources = []
		sim_sources_names = []
		sim_sources_names.append(s1)
		similar_sources.append(curr_cov)
		for s2 in normed_data:
			if max(normed_data[s2]) - min(normed_data[s1]) == 0:
				continue

			if s2 == s1:
				continue
			differences = sum(abs(np.asarray(normed_data[s1]) - np.asarray(normed_data[s2])))
			if differences < correlation_threshold:
				similar_sources.append(normed_data[s2])
				sim_sources_names.append(s2)
		if len(similar_sources) <= 1:
			continue

		plt.figure()
		t = [
			plt.plot(s, color='silver')
			for s in similar_sources
		]
		print(np.mean(np.asarray(similar_sources), axis=0))
		plt.plot(list(np.mean(np.asarray(similar_sources), axis=0)), color='blue')

		print("Sources:\n" + str([s for s in sim_sources_names]))

		#plt.show()

		def get_covered_of_src(name):
			all_coverage = []
			for per_test_data in json_data:
				for src in per_test_data['source_files']:
					if src == name:
						all_coverage.append(per_test_data['source_files'][src])
			return all_coverage

		grouping = 'similar-group-' + str(count+1)
		data_to_save[grouping] = {}
		data_to_save[grouping]['sources'] = {}
		for i in range(len(sim_sources_names)):
			data_to_save[grouping]['sources'][sim_sources_names[i]] = [str(l) for l in get_covered_of_src(sim_sources_names[i])]
		data_to_save[grouping]['source_being_compared'] = s1

	##  Save the data ##

	# Get the differences to save
	print("Gathering differences for thresholded files...")
	filt_json_data = filter_per_test_sources(json_data, filt_sources_to_plot.keys())

	test_name = test.split('/')[-1]
	_, differences = get_common_and_different(
		format_per_test_list(filt_json_data), format_per_test_list(filt_json_data),
		level='line', cov1_fname=test_name + '-1',
		cov2_fname=test_name + '-2',
	)

	# If we don't want to save all differences,
	# only save consecutive differences i.e. 0 -> 1 -> ... -> 20.
	if not args.save_all:
		new_differences = {}
		for difference in differences:
			diffname_split = difference.split('-')
			if int(diffname_split[0]) == int(diffname_split[1]) - 1:
				new_differences[difference] = differences[difference]
		differences = new_differences

	# Add location info to differences file
	for count, per_test_data in enumerate(filt_json_data):
		differences[str(count) + '-location'] = per_test_data['location']

	return differences, data_to_save


def differences_analysis(args=None, save=True, filt_and_split_data=None):
	# Plots total lines hit across all files (global variability),
	# the ratio (lines hit - mean of lines hit) for a more accurate view,
	# and an overlay of the number of lines hit in each file (in gray) with
	# a mean of those lines shown over top (in blue) for 3 figures.
	args = wrap_args(args)

	if not filt_and_split_data:
		print("Loading...")
		filt_and_split_data = check_args_and_get_data(args=args)
		if not filt_and_split_data:
			return None
		print("Done loading.")

	OUTPUT_DIR = args.output_dir if args.output_dir else os.getcwd()
	variability_threshold = args.variability_threshold
	save_all = args.save_all
	level = 'file'
	if args.line_level:
		level = 'line'

	test_groups = group_tests(filt_and_split_data)
	for test in test_groups:
		# For each test, perform the plotting mentioned above.
		print("Running test: " + test)
		json_data = test_groups[test]

		differences, data_to_save = get_and_plot_differences(json_data, args=args)

		if save:
			new_file = 'line_level_differences_' + str(int(time.time())) + ".json"
			print(
				"Saving files with changes thresholded to at least " +
				str(variability_threshold[0]) + " lines changed to: " + new_file
			)
			save_json(differences, OUTPUT_DIR, new_file)

			for grouping in data_to_save:
				new_file = 'similarity_' + grouping + '_' + str(int(time.time())) + ".json"
				print(
					"Saving similar groups of files with changes thresholded to at least " +
					str(variability_threshold[0]) + " lines changed to: " + new_file
				)
				save_json(data_to_save[grouping], OUTPUT_DIR, new_file)

		print("Close all figures to see the next test...")
		plt.show()



	return filt_and_split_data, differences


def aggregation_graph_analysis(args=None, save=True, filt_and_split_data=None):
	# Plot the same thing as 'differences', but with
	# aggregated data.
	args = wrap_args(args)

	if not filt_and_split_data:
		print("Loading...")
		filt_and_split_data = check_args_and_get_data(args=args)
		if not filt_and_split_data:
			return None
		print("Done loading.")

	OUTPUT_DIR = args.output_dir if args.output_dir else os.getcwd()
	variability_threshold = args.variability_threshold
	save_all = args.save_all
	freq_range = args.frequency_filter

	filt_and_split_data = format_to_level(filt_and_split_data, level='line')

	test_groups = group_tests(filt_and_split_data)
	for test in test_groups:
		# For each test, perform the plotting mentioned above.
		print("Running test: " + test)
		json_data = test_groups[test]

		print("Removing file variability.")
		json_data = filter_file_variability(json_data)

		test_name = test.split('/')[-1]

		print("### Aggregating reports")
		total_aggregate = {}
		aggregated_data = []
		for count, per_test_data in enumerate(json_data):
			if count >= len(json_data) - 1:
				continue
			if len(total_aggregate) == 0:
				total_aggregate = per_test_data
				continue

			total_aggregate = aggregate_reports(total_aggregate, per_test_data)
			aggregated_data.append(copy.deepcopy(total_aggregate))

		print("### Ploting aggregation report")
		differences = get_and_plot_differences(aggregated_data, test=test, plot_total_lines=False, args=args, show_stability=True)

		if save:
			new_file = 'line_level_differences_' + str(int(time.time())) + ".json"
			print(
				"Saving files with changes thresholded to at least " +
				str(variability_threshold[0]) + " lines changed to: " + new_file
			)
			save_json(differences, OUTPUT_DIR, new_file)
		plt.show()

	return filt_and_split_data


def filter_freqs_analysis(args=None, save=True, filt_and_split_data=None):
	# Plot the same thing as 'differences', but with
	# aggregated data.
	args = wrap_args(args)

	if not filt_and_split_data:
		print("Loading...")
		filt_and_split_data = check_args_and_get_data(args=args)
		if not filt_and_split_data:
			return None
		print("Done loading.")

	OUTPUT_DIR = args.output_dir if args.output_dir else os.getcwd()
	save_all = args.save_all
	freq_range = args.frequency_filter

	filt_and_split_data = format_to_level(filt_and_split_data, level='line')

	test_groups = group_tests(filt_and_split_data)
	for test in test_groups:
		# For each test, perform the plotting mentioned above.
		print("Running test: " + test)
		json_data = test_groups[test]

		print("Removing file variability.")
		json_data = filter_file_variability(json_data)

		test_name = test.split('/')[-1]

		print("Filtering frequencies...")
		new_data = filter_freqs(json_data, freq_range)

		print("Plotting filtered data")
		f1 = plt.figure()
		mean_data = []
		total_trials = len(new_data['source_files'])
		for sf in new_data['source_files']:
			plt.plot(new_data['source_files'][sf], label=sf, color='silver')
			if len(mean_data) == 0:
				mean_data = new_data['source_files'][sf]
			else:
				mean_data += new_data['source_files'][sf]
		plt.plot(np.asarray(mean_data)/total_trials, label='mean', color='blue')
		plt.title("Lines hit over time, frequency filtered")

		if save_all:
			output_name = os.path.join(OUTPUT_DIR, 'with_freqs_filter_' + str(int(time.time())) + '.png')
			print("Saving figure to: " + output_name)
			ymin, ymax = plt.ylim()
			plt.ylim(0, 4100)
			plt.savefig(output_name)
			plt.ylim(ymin, ymax)

		plt.show()

	return filt_and_split_data


def filter_ttest_analysis(args=None, save=True, filt_and_split_data=None):
	# Plot the same thing as 'differences', but with
	# aggregated data.
	args = wrap_args(args)

	if not filt_and_split_data:
		print("Loading...")
		filt_and_split_data = check_args_and_get_data(args=args)
		if not filt_and_split_data:
			return None
		print("Done loading.")

	OUTPUT_DIR = args.output_dir if args.output_dir else os.getcwd()
	save_all = args.save_all
	freq_range = args.frequency_filter

	filt_and_split_data = format_to_level(filt_and_split_data, level='line')

	test_groups = group_tests(filt_and_split_data)
	for test in test_groups:
		# For each test, perform the plotting mentioned above.
		print("Running test: " + test)
		json_data = test_groups[test]

		print("Removing file variability.")
		json_data = filter_file_variability(json_data)

		test_name = test.split('/')[-1]

		print("Searching for significant changes...")
		new_data = filter_ttest(json_data, freq_range)

		print("\n\nSignificant Changes In: ")
		for sf in new_data:
			if new_data[sf]:
				print(sf)

		if save_all:
			output_name = os.path.join(OUTPUT_DIR, 'with_freqs_filter_' + str(int(time.time())) + '.json')
			print("Saving data to: " + output_name)
			with open(output_name, "w") as f:
				json.dump(new_data, f)

	return filt_and_split_data


if __name__=="__main__":
	print("Not for use from CLI.")