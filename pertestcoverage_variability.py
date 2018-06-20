import argparse

from pertestcoverage_view import parse_view_args
from utils.cocoanalyze.analysis_types import differences_analysis, aggregation_graph_analysis


def parse_variability_args():
	parser = parse_view_args()
	#parser = argparse.ArgumentParser(parents=[view_parser])
	parser.add_argument(
		"-o", "--output-dir", type=str,
		help='Output directory for the data created (mainly jsons).'
	)
	parser.add_argument(
		"--differences", action="store_true", default=False,
		help='Set this to perform a simple differences analysis and return the ' +
			 'results in jsons in the output directory.'
	)
	parser.add_argument(
		"--aggregation-graph", action="store_true", default=False,
		help='Set this to perform an aggregation analysis of the differences, ' +
			 'or variability, over time. Little to no variability yield graphs ' +
			 'with lines that are horizontal, or very close to it, with small ' +
			 'increases over time.'
	)
	parser.add_argument(
		"--line-level", default=False,
		help='Set this to look at line level differences. If this is not set, ' +
			 'we look at file-level differences.'
	)
	parser.add_argument(
		"--split-types", action="store_true", default=False,
		help='Set this to split files into groups of c/c++, js, and etc..\n' +
			 '  C/C++:  (cpp, h, c, cc, hh, tcc)\n' +
			 '  JS:     (js, jsm)'
	)
	return parser


def main():
	# Perform a variability analysis
	args = parse_variability_args().parse_args()

	if args.differences:
		print("Running differences analysis.")
		differences_analysis(args=args)
	elif args.aggregation_graph:
		print("Running aggregation graph analysis.")
		aggregation_graph_analysis(args=args)
	else:
		print(
			"No analysis type was specified. Use --differences or something " +
			"similar found in -h."
		)


if __name__=="__main__":
	main()