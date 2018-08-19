import copy
import numpy as np
import random
from scipy import stats as scistats
from matplotlib import pyplot as plt
from cocoload import pattern_find, format_to_level, level_check


def filter_ttest(json_data_list, t_test_bounds):
	new_sampling_rate = 100
	dist_between_samples = 1/new_sampling_rate

	# Get the current level of the data
	curr_level = level_check(json_data_list[0])
	print("Number of initial data points: " + str(len(json_data_list)))
	if curr_level == 'file':
		print("Cannot filter frequencies from `file` level data.")
		return json_data_list

	# Get source files into groups across all datasets
	srcFile_groups = {}
	for per_test_data in json_data_list:
		for source in per_test_data['source_files']:
			if source not in srcFile_groups:
				srcFile_groups[source] = []
			coverage = per_test_data['source_files'][source]
			if curr_level == 'line':
				srcFile_groups[source].append(len(coverage))
			elif curr_level == 'hits':
				# TODO: Redo to give each line a timeseries.
				srcFile_groups[source].append(sum([hits for _, hits in coverage]))

	# small test
	additional = 5
	for srcFile_name in srcFile_groups:
		srcFile_data = srcFile_groups[srcFile_name]
		lastel = srcFile_data[-1]
		if 3000 > max(srcFile_data) > 2000:
			new_dat = lastel * 1.1
		else:
			new_dat = lastel
		srcFile_groups[srcFile_name].extend([new_dat * (1 + random.uniform(-0.05, 0.05)) for _ in range(additional)])

	significance_data = {'source_files': {}}
	for srcFile_name in srcFile_groups:
		srcFile_data = srcFile_groups[srcFile_name]

		mean_upsignal = np.mean(srcFile_data)

		# small test
		additional = 2
		lastel = srcFile_data[-1]
		if 3000 > max(srcFile_data) > 2000:
			new_dat = lastel * 1.02
		else:
			new_dat = lastel
		srcFile_data.extend([new_dat for _ in range(additional)])
		# First upsample the timeseries
		# (can only detect freq_max < sampling_rate/2 by Nyquist-Shanon sampling Theorem)
		upsampled_signal = np.interp(
			np.arange(0, len(srcFile_data), dist_between_samples),
			np.arange(0, len(srcFile_data), 1),
			srcFile_data
		)

		zero_signal = np.asarray([mean_upsignal for _ in upsampled_signal])

		t, p = scistats.ttest_ind(zero_signal, upsampled_signal)

		print("T-test value: " + str(t))
		significant = False
		if  t_test_bounds[0] < t or t > t_test_bounds[1]:
			significant = True

		toprint = "Change is " if significant else "Change is not "
		print(
			toprint + "significant for file: " + srcFile_name
		)
		significance_data[srcFile_name] = significant
	return significance_data



def filter_freqs(json_data_list, freqs_to_keep, downsample=False):
	# Use a brickwall filter - no need to worry about Gibb's phenomenon
	# here, we assume file variability is removed. This can
	# really only happen in very sharp drops or increases
	# in lines covered.
	#
	# Here we assume the sampling rate is 1 sample/second (Hz).
	# This is upsampled to 100 Hz, then processed with an FFT
	# filter, and downsampled again after.
	#
	# This allows us to have a solid FFT range to play with
	# and also make it easier to understand what frequencies
	# could remove which type's of code changes. For variability
	# removal, very high frequency changes should be filtered. (>)
	#
	# If no errors were encountered, the data returned is in
	# the form of a single json_data as all the files were
	# aggregated together to form a time series. (This may change).
	#
	new_sampling_rate = 100
	dist_between_samples = 1/new_sampling_rate
	low_freq = freqs_to_keep[0]
	high_freq = freqs_to_keep[1]

	if len(json_data_list) == 0:
		return json_data_list

	# Get the current level of the data
	curr_level = level_check(json_data_list[0])
	print("Number of initial data points: " + str(len(json_data_list)))
	if curr_level == 'file':
		print("Cannot filter frequencies from `file` level data.")
		return json_data_list

	# Get source files into groups across all datasets
	srcFile_groups = {}
	for per_test_data in json_data_list:
		for source in per_test_data['source_files']:
			if source not in srcFile_groups:
				srcFile_groups[source] = []
			coverage = per_test_data['source_files'][source]
			if curr_level == 'line':
				srcFile_groups[source].append(len(coverage))
			elif curr_level == 'hits':
				# TODO: Redo to give each line a timeseries.
				srcFile_groups[source].append(sum([hits for _, hits in coverage]))

	# small test
	additional = 5
	for srcFile_name in srcFile_groups:
		srcFile_data = srcFile_groups[srcFile_name]
		lastel = srcFile_data[-1]
		if 3000 > max(srcFile_data) > 2000:
			new_dat = lastel * 1.1
		else:
			new_dat = lastel
		srcFile_groups[srcFile_name].extend([new_dat * (1 + random.uniform(-0.05, 0.05)) for _ in range(additional)])

	filtered_data = {'source_files': {}}
	for srcFile_name in srcFile_groups:
		srcFile_data = srcFile_groups[srcFile_name]

		# First upsample the timeseries
		# (can only detect freq_max < sampling_rate/2 by Nyquist-Shanon sampling Theorem)
		upsampled_signal = np.interp(
			np.arange(0, len(srcFile_data), dist_between_samples),
			np.arange(0, len(srcFile_data), 1),
			srcFile_data
		)

		# Pad both ends
		init_length = len(upsampled_signal)
		upsampled_signal = np.concatenate(
			[
				upsampled_signal[0:int(len(upsampled_signal)/2)][::-1],
				upsampled_signal,
				upsampled_signal[int(len(upsampled_signal)/2):][::-1]
			]
		)

		# Get frequency domain signal
		freq_bins =  np.fft.fftfreq(upsampled_signal.size, d=dist_between_samples)
		freq_signal = np.fft.fft(upsampled_signal, n=len(upsampled_signal))

		# Filter signal
		filt_freq_signal = freq_signal.copy()
		zero_freq = copy.deepcopy(filt_freq_signal[freq_bins == 0])
		filt_freq_signal[(abs(freq_bins) < low_freq)] = 0
		filt_freq_signal[(abs(freq_bins) > high_freq)] = 0
		filt_freq_signal[freq_bins == 0] = zero_freq

		# Inverse fourier to get filtered signal
		start = int(init_length/2)
		filt_signal = np.fft.ifft(filt_freq_signal, n=len(upsampled_signal)).real
		filt_signal = filt_signal[start:start+init_length]
		if downsample:
			filtered_data['source_files'][srcFile_name] = np.interp(
				np.arange(0, len(filt_signal), 1/dist_between_samples),
				np.arange(0, len(filt_signal), 1),
				filt_signal
			)
		else:
			filtered_data['source_files'][srcFile_name] = filt_signal
	return filtered_data


def filter_per_test_sources(json_data_list, source_matchers):
	filtered_data_list = []
	for per_test_data in json_data_list:
		new_sourcefiles = {}
		for source in per_test_data['source_files']:
			if pattern_find(source, source_matchers):
				new_sourcefiles[source] = per_test_data['source_files'][source]
		if len(new_sourcefiles) > 0:
			per_test_data['source_files'] = new_sourcefiles
			filtered_data_list.append(per_test_data)
	return filtered_data_list


def filter_per_test_tests(json_data_list, test_matchers):
	filtered_data_list = []
	for per_test_data in json_data_list:
		if pattern_find(per_test_data['test'], test_matchers):
			filtered_data_list.append(per_test_data)
	return filtered_data_list


def get_total_lines_hit_in_test(per_test_data, get_files=False):
	total_lines = 0
	for source in per_test_data['source_files']:
		coverage = per_test_data['source_files'][source]
		total_lines += len(coverage)
	return total_lines


def filter_per_test_lines(json_data_list, line_range):
	if not line_range:
		return json_data_list

	too_low = line_range[0]
	too_high = line_range[1]
	filtered_data_list = []
	for per_test_data in json_data_list:
		lines_hit = get_total_lines_hit_in_test(per_test_data)
		if too_low <= lines_hit <= too_high:
			per_test_data['lines_hit'] = lines_hit
			filtered_data_list.append(per_test_data)
	return filtered_data_list


def filter_per_test_all(json_data_list, test_matchers, source_matchers, line_range):
	filtered_tests = filter_per_test_tests(json_data_list, test_matchers)
	filtered_sources = filter_per_test_sources(filtered_tests, source_matchers)
	filtered_lines = filter_per_test_lines(filtered_sources, line_range)
	return filtered_lines


def filter_file_variability(json_data_list):
	good_sources = {}
	variable_sources = {}
	for count, per_test_data in enumerate(json_data_list):
		if count == 0:
			good_sources = per_test_data['source_files'].keys()
			continue
		variable_sources = set(variable_sources) | per_test_data['source_files'].keys()
		good_sources = good_sources & per_test_data['source_files'].keys()

	variable_sources = set(variable_sources) - good_sources
	print("Good sources:")
	print(good_sources)
	print()
	print("Variable sources: ")
	print(variable_sources)

	if len(variable_sources) == 0:
		return json_data_list
	else:
		return filter_per_test_sources(json_data_list, list(good_sources))


def split_file_types(json_data_list):
	# Splits data into c/c++, js, and etc.
	# groups. The tests are split into their
	# own tests with the 'test' name append
	# with either '-c', '-js', or '-etc'
	# (even if they are empty).
	c_group = ('cpp', 'h', 'c', 'cc', 'hh', 'tcc')
	js_group = ('js', 'jsm')

	split_data = []
	for per_test_data in json_data_list:
		test_name = per_test_data['test']

		c_split = {}
		js_split = {}
		etc_split = {}
		for source in per_test_data['source_files']:
			coverage = per_test_data['source_files'][source]
			source_ftype = source.split('.')[-1]
			if source_ftype in c_group:
				c_split[source] = coverage
			elif source_ftype in js_group:
				js_split[source] = coverage
			else:
				etc_split[source] = coverage

		tmp_test = per_test_data
		tmp_test['test'] = test_name + '-c'
		tmp_test['source_files'] = c_split
		split_data.append(copy.deepcopy(tmp_test))

		tmp_test = per_test_data
		tmp_test['test'] = test_name + '-js'
		tmp_test['source_files'] = js_split
		split_data.append(copy.deepcopy(tmp_test))

		tmp_test = per_test_data
		tmp_test['test'] = test_name + '-etc'
		tmp_test['source_files'] = etc_split
		split_data.append(copy.deepcopy(tmp_test))

	return split_data


def group_tests(json_data_list):
	test_groups = {}
	for per_test_data1 in json_data_list:
		test_name = per_test_data1['test']
		if test_name in test_groups:
			continue

		test_groups[test_name] = []
		for per_test_data2 in json_data_list:
			if test_name == per_test_data2['test']:
				test_groups[test_name].append(per_test_data2)

	return test_groups
