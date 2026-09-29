.PHONY: run gui test

# One command: press key -> enter identifier -> submit -> agents run ->
# chat Q&A -> /done -> [N] new case / [Q] close case file.
run:
	./alpha cli interactive

gui:
	./alpha gui

test:
	. .venv/bin/activate && python -m pytest -q
