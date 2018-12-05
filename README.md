# Current usage of tool

First clone and run the following (Python 3 required):
```
cd coco-tools
py setup.py install
```

Then, you can use the various analysis types listed with '-l' or '--list' (extremely similar to [active-data-recipes](https://github.com/mozilla/active-data-recipes)):
```
ptc -l 		# This will list available analysis types
ptc patch_analysis -c C:\tmp\config.yml # This will run a patch analysis
```

All `ptc` analysis types take a YAML config to make it simpler to configure the algorithms (rather than passing a bunch of random flags through the CLI)

On linux you may have to do the following if you have errors with matplotlib `sudo apt-get install python3-tk`

# Coverage Scheduling Analysis Instructions 

These instructions are applicable to the analysis types (the active data version can skip step 5: fixed_by_commit_analysis_rawdata, fixed_by_commit_analysis

Steps 1-4 may be obsolete eventually if a `mach` tool could be built. i.e. (1) Query redash DB - requires keys, (2) Clean test-names, then (3) Run test-coverage on cleaned test names.

1. The first thing to do is to obtain a list of `test_fixed` entries from the `treeherder` redash database. The query must produce a CSV file with exactly 4 columns (changeset, task-name/suite, repo, test_fixed). A sample query can be found at `pertestcoverage/analysistypes/configs/querysample.txt`.

2. Modify `pertestcoverage/analysistypes/configs/config_clean_test_names.yml` to suit your needs: 1) Add the CSV files from (1) to `test-files`, 2) Set the output diretory, and 3) Set `outputteststoverify: True`. Then run (from `coco-tools/pertestcoverage/nalaysistypes/configs/` dir in these examples):
```
ptc clean_test_names -c config_clean_test_names.yml
```

3. Apply the following patch to your local mozilla-central clone: https://hg.mozilla.org/try/rev/e34fd3280759

4. Place the `tests_to_verify.json` from (2) in the `mozilla-central` folder (commit it) and run `./mach try fuzzy --full -q "'test-coverage"`.

5. (*_rawdata analysis only). Once complete, get a task ID from any of the tasks and modify `pertestcoverage/analysistypes/configs/config_artifact_downloader.yml` to add it to the `task_id` field. Run:
```
ptc artifact_downloader -c config_artifact_downloader.yml
```

OR with the default config, using `--task-id`:

```
ptc artifact_downloader -c config_artifact_downloader.yml --task-id 2RJ19daCW91
```

Once complete, the data will be contained in the output directory in a folder named by the task group ID. Both the chrome-map and the per-test-coverage data will be in the `data` folder. To simplify naming and searching, it can be easier to move the chrome-map to the top of the task group directory. IMPORTANT: (Be careful not to mix chrome-mappings between linux and windows builds).

6. Modify `config_fixed_by_commit_analaysis_rawdata.yml` to add the data you've downloaded (and the chrome-map to use) and set `analyze_all` to `True` to disable automated filtering. Setting `include_guaranteed` to `True` will incude the patches with only test-related changes in the success rate (SETA success rates include this as well). Once ready, run:
```
ptc fixed_by_commit_analysis_rawdata -c config_fixed_by_commit_analysis.yml
```

This may take some time depending on the quantity of data being analyzed, but once complete a pie chart will be displayed giving you the success rate. The total number of changesets included in the analysis is printed to the terminal, and some JSONs with information of the analysis are output in the `outputdir` location. `*_per_changeset_breakdown` might be the most interesting, as it contains information on each changeset. `*_test_matching_info.json` contains an entry for the names of tests with no data that can be used for debugging to try to obtain coverage for them.
