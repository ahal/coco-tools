## Usage example for getting per-test-coverage data:
```
py utils\artifact_downloader.py --task-group-id DAbkkBV-RjadEQAtDgjTHA --test-suites-list test-coverage-e10s --artifact-to-get per-test-coverage --unzip-artifact --output-dir ~\per-test-coverage-reports
```

This will download and unzip all coverage artifacts into the given directory so that it can be used in the tool below. Test suites must contian chunk numbers if they exist, retriggers will all be downloaded.


## Usage example for pertestcoverage_view:
```
py pertestcoverage_view.py ~\per-test-coverage-reports\DAbkkBV-RjadEQAtDgjTHA --tests dom/tests/mochitest/bugs/test_bug739038.html -s nsAppRunner.cpp
```

This tool will search through the given directory for jsons and find the ones that have the given tests that are listed and then display their unique coverage. Use -s to list files you are interested in.
