"""Poverty Probability Index scoring: deterministic, no LLM.

Loads VisionFund's PPI_scorecards.xlsx / PPI_lookups.xlsx reference
workbooks, scores each client's raw PPI answers into a 0-100 score, and
converts that score into a poverty-likelihood percentage per poverty line.
"""
