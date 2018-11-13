import os
import time
import logging
import numpy as np
import csv

from matplotlib import pyplot as plt

from ..cli import AnalysisParser

from ..utils.cocofilter import (
	find_files_in_changeset,
	find_support_files_modified,
	filter_per_test_tests
)

from ..utils.cocoload import (
	save_json,
	get_http_json,
	query_activedata,
	get_changesets,
	get_coverage_tests,
	get_coverage_tests_from_jsondatalist,
	get_all_pertest_data,
	get_all_stdptc_data,
	HG_URL,
	TYPE_PERTEST,
	TYPE_STDPTC
)

log = logging.getLogger('pertestcoverage')


def plot_histogram(data, x_labels, title, figure=None, **kwargs):
	if not figure:
		f = plt.figure()
	else:
		plt.figure(f.number)

	x = range(len(data))

	b = plt.bar(x, data, **kwargs)
	plt.xticks(x, x_labels, rotation='vertical')
	plt.title(title)

	return f, b


def run(args=None, config=None):
	"""
		Expects a `config` with the following settings:

			# To limit number of patchs if there's a lot
			numpatches: 100
			outputdir: "C:/tmp/"
			hg_analysisbranch:
				mozilla-central: "mozilla-central"
				mozill-inboun: "integration/mozilla-inbound"

			# See 'config/config_fixed_by_commit_analysis.yml' for more info on the
			# following field.
			changesets: ["path_to_csv_with_data"]

			tc_tasks_rev_n_branch: [
				["dcb3a3ba9065", "try"],
				["6369d1c6526b", "try"]
			]
	"""
	if args:
		parser = AnalysisParser('config')
		args = parser.parse_analysis_args(args)
		config = args.config
	if not config:
		raise Exception("Missing `config` dict argument.")

	numpatches = config['numpatches']
	hg_analysisbranch = config['hg_analysisbranch']
	changesets_list = config['changesets']
	outputdir = config['outputdir']
	tc_tasks_rev_n_branch = config['tc_tasks_rev_n_branch']
	pertest_rawdata_folders = config['pertest_rawdata_folders']
	analyze_all = config['analyze_all'] if 'analyze_all' in config else False
	mozcentral_path = config['mozcentral_path'] if 'mozcentral_path' in config else None

	changesets = []
	for csets_csv_path in changesets_list:
		with open(csets_csv_path, 'r') as f:
			reader = csv.reader(f)
			count = 0
			for row in reader:
				if count == 0:
					count += 1
					continue
				changesets.append(tuple(row))

	# JSONs to use for per-test test file queries
	coverage_query = {
		"from":"coverage",
		"where":{"and":[
			{"in":{"repo.changeset.id12":[rev for rev, branch in tc_tasks_rev_n_branch]}},
			{"eq":{"repo.branch.name":"try"}},
			{"eq":{"test.name":""}}
		]},
		"limit":1,
		"groupby":[{"name":"source","value":"source.file.name"}]
	}

	failed_tests_query_json = {
		"from":"unittest",
		"where":{
			"and":[
				{"eq":{"repo.changeset.id12":None}},
				{"eq":{"repo.branch.name":None}},
				{"prefix":{"run.name":"test-linux64"}},
				{"eq":{"task.state":"failed"}},
				{"eq":{"result.ok":"false"}},
				{
					"or":[
						{"prefix":{"run.suite":"mochitest"}},
						{"prefix":{"run.suite":"xpcshell"}}
					]
				}
			]
		},
		"limit":100000,
		"select":[{"name":"test","value":"result.test"}]
	}

	jsondatalist = []
	for location_entry in pertest_rawdata_folders:
		if location_entry['type'] == TYPE_PERTEST:
			jsondatalist.extend(get_all_pertest_data(location_entry['location'], chrome_map_path=location_entry['chrome-map']))
		elif location_entry['type'] == TYPE_STDPTC:
			jsondatalist.extend(get_all_stdptc_data(location_entry['location'], chrome_map_path=location_entry['chrome-map']))
	

	all_failed_ptc_tests = get_coverage_tests(tc_tasks_rev_n_branch, get_failed=True)

	tests_for_changeset = {}
	changesets_counts = {}
	tests_per_file = {}

	histogram1_datalist = []

	'''
	tests_with_no_data = ['devtools/client/webide/test/test_addons.html', 'toolkit/components/normandy/test/browser/browser_AddonStudies.js', 'browser/components/customizableui/test/browser_remote_tabs_button.js', 'dom/payments/test/test_block_none10s.html', 'browser/components/sessionstore/test/browser_async_remove_tab.js', 'devtools/server/tests/unit/test_objectgrips-fn-apply.js', 'xpcshell-remote.ini:toolkit/components/extensions/test/xpcshell/test_ext_webRequest_startup.js', 'accessible/tests/mochitest/jsat/test_content_integration.html', 'xpcshell.ini:toolkit/mozapps/extensions/test/xpcshell/test_LightweightThemeManager.js', 'devtools/client/canvasdebugger/test/browser_canvas-actor-test-09.js', 'browser/components/payments/test/mochitest/test_basic_card_form.html', 'devtools/client/webide/test/test_device_runtime.html', 'browser/base/content/test/static/browser_all_files_referenced.js', 'devtools/client/framework/test/browser_browser_toolbox_debugger.js', 'xpcshell.ini:toolkit/mozapps/extensions/test/xpcshell/test_shutdown.js', 'browser/base/content/test/performance/browser_urlbar_search.js', 'xpcshell.ini:toolkit/components/extensions/test/xpcshell/test_ext_manifest_themes.js', 'devtools/client/inspector/flexbox/test/browser_flexbox_sizing_info_for_different_writing_modes.js', 'xpcshell.ini:toolkit/mozapps/extensions/test/xpcshell/test_AddonRepository.js', 'devtools/client/shared/test/browser_dbg_listaddons.js', 'browser/components/translation/test/browser_translation_infobar.js', 'devtools/client/debugger/test/mochitest/browser_dbg_aaa_run_first_leaktest.js', 'browser/base/content/test/static/browser_parsable_css.js', 'xpcshell-remote.ini:toolkit/components/extensions/test/xpcshell/test_ext_alarms_replaces.js', 'browser/components/sessionstore/test/browser_upgrade_backup.js', 'layout/xul/test/browser_bug703210.js', 'devtools/client/inspector/grids/test/browser_grids_no_fragments.js', 'browser/base/content/test/static/browser_parsable_script.js', 'browser/extensions/onboarding/test/browser/browser_onboarding_accessibility.js', 'browser/components/tests/unit/test_browserGlue_migration_loop_cleanup.js', 'browser/components/extensions/test/browser/browser_ext_slow_script.js', 'memory/replace/dmd/test/test_dmd.js', 'browser/components/payments/test/mochitest/test_address_option.html', 'testname', 'devtools/client/webconsole/test/mochitest/browser_jsterm_completion_invalid_dot_notation.js', 'toolkit/components/telemetry/tests/unit/test_TelemetryHealthPing.js', 'devtools/client/inspector/grids/test/browser_grids_grid-list-on-iframe-reloaded.js', 'browser/base/content/test/siteIdentity/browser_tls_handshake_failure.js', 'xpcshell.ini:toolkit/mozapps/extensions/test/xpcshell/test_webextension_langpack.js', 'dom/base/test/browser_use_counters.js', 'toolkit/content/tests/widgets/xbl/test_videocontrols_keyhandler.html']
	tests_with_no_data.extend(
		['/webdriver/tests/close_window/close.py', 'file:///builds/worker/workspace/build/tests/reftest/tests/editor/reftests/1443902-2.html', '/content-security-policy/frame-src/frame-src-self-unique-origin.html', '/css/css-properties-values-api/registered-property-computation.html', 'file:///builds/worker/workspace/build/tests/reftest/tests/gfx/tests/reftest/1474722.html', 'xpcshell.ini:toolkit/mozapps/extensions/test/xpcshell/test_webextension_langpack.js', '/css/css-backgrounds/border-image-017.xht', '/dom/interfaces.html?exclude=Node', '/html/browsers/the-window-object/apis-for-creating-and-navigating-browsing-contexts-by-name/open-features-non-integer-screeny.html', '/IndexedDB/idlharness.any.sharedworker.html', 'devtools/client/framework/test/browser_browser_toolbox_debugger.js', 'xpcshell-remote.ini:toolkit/components/extensions/test/xpcshell/test_ext_alarms_replaces.js', 'dom/payments/test/test_block_none10s.html', 'devtools/client/webide/test/test_device_runtime.html', '/payment-request/idlharness.https.window.html', 'browser/components/sessionstore/test/browser_async_remove_tab.js', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/svg/fragid-shadow-3.html', 'accessible/tests/mochitest/jsat/test_content_integration.html', '/remote-playback/idlharness.window.html', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/canvas/1304353-text-global-composite-op-1.html', '/css/css-backgrounds/border-image-019.xht', '/css/css-contain/contain-layout-ink-overflow-013.html', '/html/semantics/scripting-1/the-script-element/module/dynamic-import/string-compilation-integrity-classic.sub.html', 'dom/base/test/browser_use_counters.js', '/webrtc/RTCDTMFSender-ontonechange-long.https.html', 'toolkit/content/tests/widgets/xbl/test_videocontrols_keyhandler.html', 'toolkit/components/telemetry/tests/unit/test_TelemetryHealthPing.js', '/html/semantics/embedded-content/media-elements/video_008.htm', '/css/css-values/viewport-units-css2-001.html', '/content-security-policy/img-src/img-src-self-unique-origin.html', '/css/CSS2/backgrounds/background-position-126.xht', 'toolkit/components/normandy/test/browser/browser_AddonStudies.js', 'browser/base/content/test/static/browser_parsable_script.js', 'xpcshell.ini:toolkit/mozapps/extensions/test/xpcshell/test_LightweightThemeManager.js', '/css/css-masking/mask-image/mask-image-url-remote-mask.html', '/webrtc/RTCRtpTransceiver.https.html', '/content-security-policy/img-src/icon-blocked.sub.html', '/payment-request/PaymentMethodChangeEvent/methodDetails-attribute.https.html', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/forms/input/shadow-rules.html', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/box-properties/box-sizing-minmax-width.html', '/content-security-policy/securitypolicyviolation/targeting.html', '/shadow-dom/slots-fallback-in-document.html', 'browser/components/customizableui/test/browser_remote_tabs_button.js', '/css/vendor-imports/mozilla/mozilla-central-reftests/masking/mask-opacity-1e.html', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/bugs/1425243-1.html', 'browser/base/content/test/static/browser_all_files_referenced.js', '/infrastructure/webdriver/tests/test_load_file.py', '/payment-request/allowpaymentrequest/allowpaymentrequest-attribute-cross-origin-bc-containers.https.html', '/webdriver/tests/actions/bounds.py', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/text-overflow/selection.html', 'devtools/client/debugger/test/mochitest/browser_dbg_aaa_run_first_leaktest.js', '/2dcontext/imagebitmap/createImageBitmap-invalid-args.html', 'devtools/server/tests/unit/test_objectgrips-fn-apply.js', 'devtools/client/inspector/flexbox/test/browser_flexbox_sizing_info_for_different_writing_modes.js', 'browser/base/content/test/performance/browser_urlbar_search.js', '/url/failure.html', 'devtools/client/shared/test/browser_dbg_listaddons.js', 'testname', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/css-ui-invalid/default-style/input-focus.html', '/css/css-images/gradient/color-stops-parsing.html', '/encoding/idlharness.https.any.serviceworker.html', '/_mozilla/binast/large.https.html', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/text-stroke/webkit-text-stroke-property-002.html', 'devtools/client/inspector/grids/test/browser_grids_no_fragments.js', 'browser/base/content/test/siteIdentity/browser_tls_handshake_failure.js', 'http://localhost:33563/1535065648057/187/deferred-anchor.xhtml#d', '/mediacapture-record/idlharness.window.html', 'devtools/client/webconsole/test/mochitest/browser_jsterm_completion_invalid_dot_notation.js', '/css/css-backgrounds/border-image-020.xht', 'browser/extensions/onboarding/test/browser/browser_onboarding_accessibility.js', 'xpcshell-remote.ini:toolkit/components/extensions/test/xpcshell/test_ext_webRequest_startup.js', '/2dcontext/drawing-text-to-the-canvas/2d.text.draw.baseline.alphabetic.html', 'xpcshell.ini:toolkit/components/extensions/test/xpcshell/test_ext_manifest_themes.js', '/webdriver/tests/element_send_keys/interactability.py', '/cookies/http-state/name-tests.html', '/mediacapture-image/ImageCapture-creation.https.html', '/fullscreen/idlharness.window.html', '/html/rendering/non-replaced-elements/the-fieldset-element-0/legend-position-relative.html', '/media-capabilities/idlharness.any.worker.html', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/font-face/variation-format-hint-1a.html', 'xpcshell.ini:toolkit/mozapps/extensions/test/xpcshell/test_AddonRepository.js', '/html/webappapis/dynamic-markup-insertion/opening-the-input-stream/bailout-exception-vs-return-origin.sub.window.html', '/webdriver/tests/minimize_window/user_prompts.py', '/fetch/api/request/destination/fetch-destination.https.html', 'devtools/client/webide/test/test_addons.html', '/webaudio/the-audio-api/the-audiobuffersourcenode-interface/audiobuffersource-channels.html', 'layout/xul/test/browser_bug703210.js', 'browser/base/content/test/static/browser_parsable_css.js', 'xpcshell.ini:toolkit/mozapps/extensions/test/xpcshell/test_shutdown.js', '/web-animations/interfaces/KeyframeEffect/idlharness.window.html', 'browser/components/extensions/test/browser/browser_ext_slow_script.js', 'devtools/client/inspector/grids/test/browser_grids_grid-list-on-iframe-reloaded.js', '/cookies/http-state/general-tests.html', 'browser/components/tests/unit/test_browserGlue_migration_loop_cleanup.js', '/fullscreen/api/element-request-fullscreen-active-document.html', '/streams/piping/pipe-through.dedicatedworker.html', 'browser/components/payments/test/mochitest/test_basic_card_form.html', '/WebCryptoAPI/generateKey/failures_AES-CBC.https.any.worker.html', '/webdriver/tests/accept_alert/accept.py', '/fetch/api/response/response-static-redirect.html', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/layers/forced-bg-color-outside-visible-region.html', 'memory/replace/dmd/test/test_dmd.js', '/fetch/cors-rfc1918/idlharness.tentative.any.sharedworker.html', 'browser/components/payments/test/mochitest/test_address_option.html', 'file:///builds/worker/workspace/build/tests/reftest/tests/layout/reftests/xul/treetwisty-svg-context-paint-1.xul', '/compat/webkit-pseudo-element.html', 'browser/components/sessionstore/test/browser_upgrade_backup.js', '/picture-in-picture/idlharness.window.html', '/html/rendering/non-replaced-elements/flow-content-0/dialog.html', '/fetch/api/request/destination/fetch-destination-no-load-event.https.html']
	)
	'''
	tests_with_no_data = ['2d.text.draw.baseline.alphabetic.html', 'testname', 'perf_reftest', 'variation-format-hint-1a.html', 'spv-only-sent-to-initiator.sub.html', '1443902-2.html', 'selection.html', 'mask-composite-1c.html', 'shadow-rules.html', 'fragid-shadow-3.html', 'box-sizing-minmax-width.html', 'page-width-3.9in.html', '1425243-1.html', 'treetwisty-svg-context-paint-1.xul', 'fragid-shadow-3.html', 'variation-format-hint-1a.html', '1304353-text-global-composite-op-1.html', 'forced-bg-color-outside-visible-region.html', 'bounds.py', 'short.mp4.lastframe.html', '1474722.html', 'input-focus.html', 'iframe-deferred-anchor.xhtml', 'webkit-text-stroke-property-002.html']
	tests_with_no_data.extend(
		['idlharness.tentative.any.sharedworker.html', '1304353-text-global-composite-op-1.html', 'tall--32px-auto--nonpercent-width-nonpercent-height.html', 'idlharness.window.html', 'shadow-rules.html', 'bailout-exception-vs-return-origin.sub.window.html', 'fragid-shadow-3.html', 'deferred-anchor.xhtml', '1425243-1.html', 'idlharness.window.html', '1474722.html', 'forced-bg-color-outside-visible-region.html', 'idlharness.window.html', '2d.text.draw.baseline.alphabetic.html', 'idlharness.window.html', 'treetwisty-svg-context-paint-1.xul', 'input-focus.html', 'box-sizing-minmax-width.html', 'webkit-text-stroke-property-002.html', 'legend-position-relative.html', 'stream-safe-creation.any.worker.html', 'idlharness.any.worker.html', 'mask-composite-1c.html', 'idlharness.https.window.html', 'perf_reftest', 'selection.html', 'bounds.py', 'idlharness.any.sharedworker.html', 'idlharness.https.any.serviceworker.html', 'short.mp4.lastframe.html', 'class-id-attr-selector-invalidation-01.html', '468263-2.html', 'testname', 'idlharness.window.html', 'img-and-image-1.html', 'webkit-pseudo-element.html']
	)

	# For each patch
	changesets_removed = {}
	count_changesets_processed = 0
	all_changesets = []
	num_guaranteed = 0
	for count, tp in enumerate(changesets):
		if count_changesets_processed >= numpatches:
			continue

		if len(tp) == 4:
			changeset, _, repo, test_fixed = tp
		else:
			cov_exists, status, code, changeset, _, repo, test_fixed, _ = tp

			if 'test' in status:
				continue

		test_fixed = test_fixed.split('=')[-1]
		test_fixed = test_fixed.split('?')[0]
		test_fixed = test_fixed.split('/')[-1]
		test_fixed = test_fixed.split('#')[0]

		if test_fixed.startswith("xpcshell.ini:"):
			continue
		found_bad = False
		for t in tests_with_no_data:
			if test_fixed in t:
				found_bad = True
				break
		if found_bad:
			continue

		changeset = changeset[:12]

		log.info("")
		log.info("On changeset " + "(" + str(count) + "): " + changeset)

		# Get patch
		currhg_analysisbranch = hg_analysisbranch[repo]
		files_url = HG_URL + currhg_analysisbranch + "/json-info/" + changeset
		data = get_http_json(files_url)
		files_modified = data[changeset]['files']
		orig_files_modified = files_modified.copy()

		# Filter modified files to only exclude all test or test helper files
		if not analyze_all:
			support_files = []
			if mozcentral_path:
				support_files = find_support_files_modified(files_modified, test_fixed, mozcentral_path)
				log.info("Support-files found in files modified: " + str(support_files))

			files_modified = list(set(files_modified) - set(support_files))
			files_modified = [
				f for f in files_modified
				if '/test/' not in f and '/tests/' not in f and 'testing/' not in f
			]
			files_modified = [
				f for f in files_modified
				if ('.js' in f and not f.endswith('.json')) or \
				   '.cpp' in f or f.endswith('.h') or f.endswith('.c')
			]

			new, _, _ = find_files_in_changeset(changeset, repo)
			new = [n.lstrip('/') for n in new]
			files_modified = list(set(files_modified) - set(new))

			if len(files_modified) == 0:
				changesets_removed[changeset] = {}
				changesets_removed[changeset]['support/test files modified'] = orig_files_modified
				log.info("No files modified after filtering test-only or support files.")
				num_guaranteed += 1
				continue

		# Get tests that use this patch
		failed_tests_query_json['where']['and'][0] = {"eq": {"repo.changeset.id12": changeset}}
		failed_tests_query_json['where']['and'][1] = {"eq": {"repo.branch.name": repo}}

		all_tests = []
		failed_tests = []

		try:
			failed_tests = query_activedata(failed_tests_query_json)
		except Exception as e:
			log.info("Error running query: " + str(failed_tests_query_json))

		all_tests = get_coverage_tests_from_jsondatalist(jsondatalist, get_files=files_modified)

		all_failed_tests = []
		if 'test' in failed_tests:
			all_failed_tests = [test for test in failed_tests['test']]

		if test_fixed in all_failed_tests:
			log.info("Test was not completely fixed by commit: " + str(test_fixed))
			continue
		else:
			log.info("Test was truly fixed. Failed tests: " + str(all_failed_tests))

		#all_tests_not_run = list(set([test_fixed]) - set(all_tests))
		# Modified for analysis 4
		found = False
		all_tests_not_run = []
		for test in all_tests:
			if test_fixed in test:
				test_fixed = test
				found = True
				break
		if not found:
			all_tests_not_run.append(test_fixed)

		log.info("Number of tests: " + str(len(all_tests)))
		log.info("Number of failed tests: " + str(len([test_fixed])))
		log.info("Number of files: " + str(len(files_modified)))
		log.info("Number of tests not scheduled by per-test: " + str(len(all_tests_not_run)))
		log.info("Tests not scheduled: \n" + str(all_tests_not_run))

		cset_count = 1
		if changeset not in changesets_counts:
			changesets_counts[changeset] = cset_count
		else:
			changesets_counts[changeset] += 1
			cset_count = changesets_counts[changeset]

		changeset_name = changeset + "_" + str(cset_count)
		tests_for_changeset[changeset_name] = {
			'patch-link': HG_URL + currhg_analysisbranch + "/rev/" + changeset,
			'numfiles': len(files_modified),
			'numtests': len(all_tests),
			'numtestsfailed': 1,
			'numtestsnotrun': len(all_tests_not_run),
			'reasons_not_run': '' if len(all_tests_not_run) == 0 else 'no_coverage_link_with_test',
			'files_modified': files_modified,
			'testsnotrun': all_tests_not_run,
		}

		for test in all_tests_not_run:
			coverage_data = filter_per_test_tests(jsondatalist, test)
			if not coverage_data:
				tests_for_changeset[changeset_name]['reasons_not_run'] =  'no_coverage_json_for_test'
  
		log.info("Reason not run (if any): " + tests_for_changeset[changeset_name]['reasons_not_run'])

		all_changesets.append(changeset)
		histogram1_datalist.append((1, 1-len(all_tests_not_run), changeset))
		count_changesets_processed += 1

		numchangesets = len(all_changesets) + num_guaranteed
		total_correct = sum([
				1 if not tests_for_changeset[cset + "_1"]['reasons_not_run'] else 0
				for cset in all_changesets
		]) + num_guaranteed
		log.info("Running success rate = {:3.2f}%".format(float((100 * (total_correct/numchangesets)))))

	log.info("")

	## Save results (number, and all tests scheduled)
	if outputdir:
		log.info("\nSaving results to output directory: " + outputdir)
		save_json(tests_for_changeset, outputdir, str(int(time.time())) + '_per_changeset_breakdown.json')
		save_json(changesets_removed, outputdir, str(int(time.time())) + '_changesets_with_only_test_or_support_files.json')

	# Plot a second bar on top
	f = plt.figure()

	numchangesets = len(all_changesets) + num_guaranteed
	total_correct = sum([
			1 if not tests_for_changeset[cset + "_1"]['reasons_not_run'] else 0
			for cset in all_changesets
	]) + num_guaranteed
	total_no_coverage_data = sum([
			1 if tests_for_changeset[cset + "_1"]['reasons_not_run'] == 'no_coverage_json_for_test' else 0
			for cset in all_changesets
	])
	total_no_coverage_link = sum([
			1 if tests_for_changeset[cset + "_1"]['reasons_not_run'] == 'no_coverage_link_with_test' else 0
			for cset in all_changesets
	])

	b2 = plt.pie(
		[
			100 * (total_correct/numchangesets),
			100 * (total_no_coverage_data/numchangesets) + 100 * (total_no_coverage_link/numchangesets)
		],
		colors=['green', 'red'],
		labels=[
			'Successfully scheduled with per-test coverage data',
			'Not successfully scheduled'
		],
		autopct='%1.1f%%'
	)

	plt.legend()

	f2 = plt.figure()

	b2 = plt.pie(
		[
			100 * (total_correct/numchangesets),
			100 * (total_no_coverage_data/numchangesets),
			100 * (total_no_coverage_link/numchangesets)
		],
		colors=['green', 'red', 'orange'],
		labels=[
			'Successfully scheduled with per-test coverage data',
			'No data found in treeherder',
			'No coverage link between source files modified and test fixed'
		],
		autopct='%1.1f%%'
	)

	plt.legend()

	log.info("Total number of changesets in pie chart: " + str(numchangesets))

	log.info("Close figures to end analysis.")
	log.info("Changesets analyzed (use these in other analysis types if possible): \n" + str(all_changesets))
	plt.show()

