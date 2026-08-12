"""Hand-written orchestration: plain Python that calls the deterministic modules and the two
LLM chains in a fixed sequence and assembles a real report-section Pydantic object.

Not an agent and not a tool -- nothing here lets an LLM choose what to call or skip a step.
Independent work (e.g. the qualitative full-dataset pass and the writer calls that don't
depend on it) runs concurrently via a plain ThreadPoolExecutor; anything that depends on a
prior step's output runs after it, in order. This is the pre-LangGraph version of the
pipeline -- the same call sequence becomes a graph later, with proper parallel fan-out and
checkpointing, once this hand-written version has proven the wiring is correct.
"""
