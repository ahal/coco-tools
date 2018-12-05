import os
import time
import logging
import numpy as np
import csv

from matplotlib import pyplot as plt

from ..cli import AnalysisParser

from ..utils.cocofilter import (
	fix_names,
	find_files_in_changeset,
	find_support_files_modified,
	filter_per_test_tests,
	get_tests_with_no_data
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
	format_testname,
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
	runname = config['runname'] if 'runname' in config else None
	include_guaranteed = config['include_guaranteed'] if 'include_guaranteed' in  config else False
	use_active_data = config['use_active_data'] if 'use_active_data' in config else False

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
			{"regexp":{"test.name":""}}
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
	if not use_active_data:
		for location_entry in pertest_rawdata_folders:
			if location_entry['type'] == TYPE_PERTEST:
				print('here')
				jsondatalist.extend(get_all_pertest_data(location_entry['location'], chrome_map_path=location_entry['chrome-map']))
			elif location_entry['type'] == TYPE_STDPTC:
				print('here2')
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
	#tests_with_no_data = ['border-image-017', 'border-image-019', 'pipe-through', 'accept', 'minimize_window/user_prompts', 'close_window', 'test_load_file', 'properties-value-inherit-001', 'Node', 'canvas/1304353-text-global-composite-op-1', 'vector/tall--32px-auto--nonpercent-width-nonpercent-height', 'input/shadow-rules', 'svg/fragid-shadow-3', '187/deferred-anchor', 'bugs/1425243-1', 'reftest/1474722', 'layers/forced-bg-color-outside-visible-region', 'drawing-text-to-the-canvas/2d', 'xul/treetwisty-svg-context-paint-1', 'default-style/input-focus', 'box-properties/box-sizing-minmax-width', 'text-stroke/webkit-text-stroke-property-002', 'the-fieldset-element-0/legend-position-relative', 'masking/mask-composite-1c', 'tests/perf_reftest', 'text-overflow/selection', 'actions/bounds', 'reftest/short', 'selectors4/class-id-attr-selector-invalidation-01', 'reftests/468263-2', 'tests/testname', 'as-image/img-and-image-1', 'compat/webkit-pseudo-element']
	
	# Ignore for analysis 8 & 9
	#tests_with_no_data = ['block-string-assignment-to-Location-assign', 'back/back','location-prototype-setting-same-origin-domain', 'user_prompts', 'border-image-017', 'border-image-019', 'pipe-through', 'accept', 'minimize_window/user_prompts', 'close_window', 'test_load_file', 'properties-value-inherit-001', 'Node', 'svg/fragid-shadow-3', 'opening-the-input-stream/abort-refresh-immediate', 'vector/tall--32px-auto--nonpercent-width-nonpercent-height', 'drawing-text-to-the-canvas/2d', 'bugs/467444-1', 'opening-the-input-stream/ignore-opens-during-unload', 'masking/mask-opacity-1e', 'text-overflow/xulscroll', 'svg/foreignObject-img', 'the-fieldset-element-0/legend-position-relative', 'input/shadow-rules', 'shared-array-buffers/nested-worker-success-dedicatedworker', 'tests/perf_reftest', 'controlling-ua/reconnectToPresentation_notfound_error', 'svg/fragid-shadow-3', 'text/hyphenation-control-5', 'xul/treetwisty-svg-context-paint-1', 'canvas/1304353-text-global-composite-op-1', 'reftests/blending-svg-root', 'cors/cors-safelisted-request-header', 'xul/treetwisty-svg-context-paint-1', 'tests/testname', 'bugs/508816-1', 'bugs/1425243-1', 'reftests/468263-2']
	#tests_with_no_data += ['svg/fragid-shadow-3', 'opening-the-input-stream/abort-refresh-immediate', 'vector/tall--32px-auto--nonpercent-width-nonpercent-height', 'drawing-text-to-the-canvas/2d', 'bugs/467444-1', 'opening-the-input-stream/ignore-opens-during-unload', 'masking/mask-opacity-1e', 'text-overflow/xulscroll', 'svg/foreignObject-img', 'the-fieldset-element-0/legend-position-relative', 'input/shadow-rules', 'shared-array-buffers/nested-worker-success-dedicatedworker', 'tests/perf_reftest', 'controlling-ua/reconnectToPresentation_notfound_error', 'svg/fragid-shadow-3', 'text/hyphenation-control-5', 'xul/treetwisty-svg-context-paint-1', 'canvas/1304353-text-global-composite-op-1', 'reftests/blending-svg-root', 'cors/cors-safelisted-request-header', 'xul/treetwisty-svg-context-paint-1', 'tests/testname', 'bugs/508816-1', 'bugs/1425243-1', 'reftests/468263-2']

	# Ignore for analysis 7
	#tests_with_no_data.extend(['browser/extensions/onboarding/test/browser/browser_onboarding_accessibility.js', 'toolkit/components/extensions/test/xpcshell/test_ext_legacy_extension_embedding.js', 'browser/base/content/test/trackingUI/browser_trackingUI_trackers_subview.js', 'browser/components/sessionstore/test/browser_async_remove_tab.js', 'browser/extensions/pdfjs/test/browser_pdfjs_savedialog.js', 'toolkit/components/extensions/test/xpcshell/test_ext_telemetry.js', 'browser/components/originattributes/test/browser/browser_firstPartyIsolation.js', 'browser/components/uitour/test/browser_UITour.js', 'browser/base/content/test/general/browser_contextmenu.js', 'devtools/client/webide/test/test_toolbox.html', 'toolkit/components/extensions/test/xpcshell/test_ext_webRequest_startup.js', 'browser/base/content/test/forms/browser_selectpopup.js', 'devtools/client/inspector/grids/test/browser_grids_no_fragments.js', 'dom/base/test/browser_force_process_selector.js', 'dom/canvas/test/webgl-conf/generated/test_2_conformance2__vertex_arrays__vertex-array-object.html', 'browser/components/tests/unit/test_browserGlue_migration_loop_cleanup.js', 'dom/payments/test/test_block_none10s.html', 'browser/components/payments/test/mochitest/test_basic_card_form.html', 'browser/extensions/screenshots/test/browser/browser_screenshots_ui_check.js', 'toolkit/components/extensions/test/xpcshell/test_ext_topSites.js', 'dom/base/test/test_script_loader_js_cache.html', 'toolkit/components/extensions/test/xpcshell/test_ext_alarms_replaces.js', 'browser/base/content/test/static/browser_misused_characters_in_strings.js', 'toolkit/components/extensions/test/xpcshell/test_ext_contentscript_create_iframe.js', 'devtools/client/webide/test/test_addons.html', 'browser/components/translation/test/browser_translation_infobar.js', 'dom/base/test/browser_use_counters.js', 'browser/base/content/test/siteIdentity/browser_tls_handshake_failure.js', 'devtools/client/debugger/test/mochitest/browser_dbg_aaa_run_first_leaktest.js', 'browser/components/extensions/test/browser/test-oop-extensions/browser_ext_popup_select.js', 'devtools/client/shared/test/browser_dbg_listaddons.js', 'devtools/client/webconsole/test/mochitest/browser_jsterm_completion_invalid_dot_notation.js', 'browser/base/content/test/urlbar/browser_autocomplete_enter_race.js', 'devtools/client/debugger/test/mochitest/browser_dbg_split-console-keypress.js', 'devtools/client/styleeditor/test/browser_styleeditor_media_sidebar_links.js', 'devtools/client/inspector/grids/test/browser_grids_grid-list-on-iframe-reloaded.js', 'browser/components/urlbar/tests/unit/test_UrlbarInput_unit.js', 'testname', 'browser/base/content/test/static/browser_parsable_css.js', 'browser/base/content/test/static/browser_all_files_referenced.js', 'dom/canvas/test/webgl-conf/generated/test_2_conformance2__textures__misc__npot-video-sizing.html', 'memory/replace/dmd/test/test_dmd.js', 'browser/base/content/test/general/browser_storagePressure_notification.js', 'dom/canvas/test/webgl-conf/generated/test_2_conformance2__rendering__framebuffer-texture-changing-base-level.html', 'devtools/client/webide/test/test_device_runtime.html'])

	tmp_tests = []
	for count, tp in enumerate(changesets):
		if len(tp) == 4:
			changeset, suite, repo, test_fixed = tp
		else:
			cov_exists, status, code, changeset, suite, repo, test_fixed, _ = tp

		test_fixed = test_fixed.split('ini:')[-1]
		if 'mochitest' not in suite and 'xpcshell' not in suite:
			test_fixed = format_testname(test_fixed)
		tmp_tests.append(test_fixed)

	tests_with_no_data = []
	if not use_active_data:
		tests_with_no_data = get_tests_with_no_data(jsondatalist, tmp_tests)
	else:
		for test_matcher in tmp_tests:
			coverage_query['where']['and'][2]['regexp']['test.name'] = ".*" + test_matcher.replace('\\', '/') + '.*'
			coverage_data = query_activedata(coverage_query)
			if len(coverage_data) == 0:
				tests_with_no_data.append(test_matcher)
	log.info("Number of tests with no data: %s" % str(len(tests_with_no_data)))
	log.info("Number of tests in total: %s" % str(len(tmp_tests)))

	# For each patch
	changesets_removed = {}
	count_changesets_processed = 0
	all_changesets = []
	num_guaranteed = 0
	for count, tp in enumerate(changesets):
		if count_changesets_processed >= numpatches:
			continue

		if len(tp) == 4:
			changeset, suite, repo, test_fixed = tp
		else:
			cov_exists, status, code, changeset, suite, repo, test_fixed, _ = tp

			if 'test' in status:
				continue

		orig_test_fixed = test_fixed
		test_fixed = test_fixed.split('ini:')[-1]
		if 'mochitest' not in suite and 'xpcshell' not in suite:
			test_fixed = format_testname(test_fixed)

		found_bad = False
		for t in tests_with_no_data:
			if test_fixed in t or t in test_fixed:
				found_bad = True
				break
		if found_bad:
			continue

		changeset = changeset[:12]

		log.info("")
		log.info("On changeset " + "(" + str(count) + "): " + changeset)
		log.info("Running analysis: %s" % str(runname))
		log.info("Test name: %s" % test_fixed)

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

			# We don't have coverage on new files
			new, _, _ = find_files_in_changeset(changeset, repo)
			new = [n.lstrip('/') for n in new]
			files_modified = list(set(files_modified) - set(new))

			if len(files_modified) == 0:
				changesets_removed[changeset] = {}
				changesets_removed[changeset]['support/test files modified'] = orig_files_modified
				log.info("No files modified after filtering test-only or support files.")
				if include_guaranteed:
					num_guaranteed += 1
					changeset_name = changeset + "_" + str(cset_count)
					tests_for_changeset[changeset_name] = {
						'patch-link': HG_URL + currhg_analysisbranch + "/rev/" + changeset,
						'numfiles': len(orig_files_modified),
						'numtests': 1,
						'numtestsfailed': 1,
						'numtestsnotrun': len(all_tests_not_run),
						'reasons_not_run': '',
						'files_modified': orig_files_modified,
						'suite': suite,
						'runname': runname,
						'test-related': test_fixed,
						'testsnotrun': [],
					}
				continue

			files_modified = [
				f for f in files_modified
				if ('.js' in f and not f.endswith('.json')) or \
				   '.cpp' in f or f.endswith('.h') or f.endswith('.c')
			]
			if len(files_modified) == 0:
				log.info("No files left after removing unrelated changes.")
				continue

		# Get tests that use this patch
		failed_tests_query_json['where']['and'][0] = {"eq": {"repo.changeset.id12": changeset}}
		failed_tests_query_json['where']['and'][1] = {"eq": {"repo.branch.name": repo}}

		all_tests = []
		failed_tests = []
		try:
			failed_tests = query_activedata(failed_tests_query_json)
		except Exception as e:
			log.info("Error running query: " + str(test_coverage_query_json))

		if use_active_data:
			try:
				all_tests = get_coverage_tests(tc_tasks_rev_n_branch, get_files=files_modified)
			except Exception as e:
				log.info("Error running query: " + str(test_coverage_query_json))
		else:
			all_tests = get_coverage_tests_from_jsondatalist(jsondatalist, get_files=files_modified)

		all_failed_tests = []
		if 'test' in failed_tests:
			all_failed_tests = [test for test in failed_tests['test']]

		if pattern_find(test_fixed, all_failed_tests):
			log.info("Test was not completely fixed by commit: " + str(test_fixed))
			continue

		log.info("Test was truly fixed. Failed tests: " + str(all_failed_tests))

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
			'suite': suite,
			'runname': runname,
			'testsnotrun': all_tests_not_run,
		}

		if use_active_data:
			for test in all_tests_not_run:
				if test in all_failed_ptc_tests:
					tests_for_changeset[changeset_name]['reasons_not_run'] = 'failed_test'
					continue

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
		timestr = str(int(time.time()))
		save_json(tests_for_changeset, outputdir, timestr + '_per_changeset_breakdown.json')
		save_json(changesets_removed, outputdir, timestr + '_changesets_with_only_test_or_support_files.json')
		save_json(
			{
				'testswithnodata': fix_names(changesets, tests_with_no_data),
				'alltests-matchers': tmp_tests,
			},
			outputdir,
			timestr + '_test_matching_info.json'
		)

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

	log.info("Completed analysis for run: %s" % str(runname))

	log.info("Total number of changesets in pie chart: " + str(numchangesets))

	log.info("Close figures to end analysis.")
	log.info("Changesets analyzed (use these in other analysis types if possible): \n" + str(all_changesets))
	plt.show()

