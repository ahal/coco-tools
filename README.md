# Current usage of tool

First clone and run the following:
```
cd coco-tools
py setup.py install
```

Then, you can use the various analysis types listed with '-l' or '--list' (extremely similar to [active-data-recipes](https://github.com/mozilla/active-data-recipes)):
```
ptc -l 		# This will list available analysis types
ptc patch_analysis -c C:\tmp\config.yml # This will run a patch analysis
```

All ptc analysis types take a YAML config to make it simpler to configure the algorithms (rather than passing a bunch of random flags through the CLI)


# OLD USAGE BELOW

## Usage example for getting per-test-coverage data:
```
py utils\artifact_downloader.py --task-group-id DAbkkBV-RjadEQAtDgjTHA --test-suites-list test-coverage-e10s --artifact-to-get per-test-coverage --unzip-artifact --output ~\per-test-coverage-reports
```

This will download and unzip all coverage artifacts into the given directory so that it can be used in the tool below. Test suites must contian chunk numbers if they exist, retriggers will all be downloaded.


## Usage example for pertestcoverage_view:
```
py pertestcoverage_view.py ~\per-test-coverage-reports\DAbkkBV-RjadEQAtDgjTHA --tests dom/tests/mochitest/bugs/test_bug739038.html -s nsAppRunner.cpp
```

This tool will search through the given directory for jsons and find the ones that have the given tests that are listed and then display their unique coverage. Use -s to list files you are interested in.


## Usage example for pertestcoverage_variability analysis:
```
py pertestcoverage_variability.py  ~\per-test-coverage-reports\EKzK4lJ3Rt2BH3zDGVdXjA\0\test-coverage-e10s -t test_bug --differences --line-range 0 10000000 --variability-threshold 50 100 -o ~\data_holder
```

This tool will save all the consecutive differences between the given files (--save-all to save all differences), where the files compared are determined by the range --variability-threshold which defines the min and max number of lines changed from one run to another. --line-range determines how large the per-test-coverage JSON should be in number of lines hit - used to restrict multiple test JSONs within the same folder from being used (if a test has atleast 0 to 10000000 lines it is kept in this case). The graphs show the total line hits per test, the change relative to the mean hits, and the coverage for each file overtime with the mean overlaid onto the plots (in blue). Restrict the files seen here, and saved by using --variability-threshold.


```
py pertestcoverage_variability.py  ~\per-test-coverage-reports\EKzK4lJ3Rt2BH3zDGVdXjA\0\test-coverage-e10s -t test_bug --aggregation-graph --line-range 0 10000000 --variability-threshold 50 100 -o ~\data_holder
```

Using --aggregation-graph will perform an aggregated comparison, aggregating all reports found, and then displaying the total number of lines hit across all files (overlaid onto the mean) over time. Low variability will show a line that may be increasing but is close to the horizontal. High variability shows exponentially increasing line counts with little slowdown (or does not approach the horizontal slope of 0).