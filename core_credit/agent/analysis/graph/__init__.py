"""LangGraph port of the Business & Household Impact (Part 3) driver.

Same call sequence as driver/build_business_household_impact.py, expressed as a graph so the
qualitative batch fan-out gets proper Send-based parallelism (instead of a hand-rolled
ThreadPoolExecutor) and the whole run gets checkpointed -- a crash partway through the ~10
minute qualitative pass no longer means starting over.

One real mechanic worth knowing before reading nodes.py: a node with multiple incoming edges
of different path lengths (here, assemble_section_node has one path through the batch-fan-out
+ merge + insight, which takes more supersteps than the direct income/qol write paths) does
NOT wait for every predecessor before its first run -- LangGraph runs it once per superstep in
which any predecessor fires. Confirmed empirically with a toy graph before writing this.
assemble_section_node is therefore written defensively: it only produces the final `section`
once every required field is actually present, and is a harmless no-op otherwise.
"""
