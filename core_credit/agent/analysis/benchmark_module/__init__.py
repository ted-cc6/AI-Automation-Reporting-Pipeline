"""External benchmark integration: 60 Decibels MFI Index + national poverty rates.

Loads VisionFund's External Benchmarks.xlsx, deterministic, no LLM. Produces
BenchmarkComparison objects (for the MFI Index overlay used across most
sections) and CountryVsNationalRate objects (for the Poverty Likelihood
section's 2.2 subsection), both already defined in schemas/.

"Internal regional and global" benchmarks are deliberately NOT part of this
module -- those are our own survey data rolled up by region/overall, which
the metrics engine already produces (crosstab_by_segment on SegmentAxis.REGION,
or just the overall share). This module only ever supplies external figures.
"""
