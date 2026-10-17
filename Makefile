PYTHON ?= python3

.PHONY: test run
test:
	$(PYTHON) -m unittest discover -s tests -v

run:
	$(PYTHON) src/generate_trace.py
	$(PYTHON) src/benchmark.py --out results
	$(PYTHON) src/benchmark.py --suite --out results/suite
