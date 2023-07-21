.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash

UNAME_S := $(shell uname -s)
PYENV_NAME := $(notdir $(CURDIR))
PYTHON_VERSION := 3.11.2


PYTHON_PACKAGES := \
	pipreqs black flake8 \
	playwright

.PHONY: format
format: deps  ## Auto-format and check pep8
	  black --line-length 119 *.py && flake8 --max-line-length=119 *.py

deps:  ## Ensure OS Dependencies (Only works for MacOS)
ifeq ($(UNAME_S),Darwin)
	@# Check only for MacOS
	@for dep in brew pyenv pyenv-virtualenv; do \
	  if ! which $$dep 2>&1 > /dev/null; then echo "Please install $$dep"; fi; \
	done;
endif

pyenv: deps  ## Create the pyenv for Python development
	@if ! pyenv versions | grep $(PYTHON_VERSION) 2>&1 > /dev/null; then \
	  pyenv install $(PYTHON_VERSION); \
	fi
	@if ! pyenv virtualenvs | grep $(PYENV_NAME) 2>&1 > /dev/null; then \
	  pyenv virtualenv $(PYTHON_VERSION) $(PYENV_NAME); \
	fi
	@if ! pyenv local 2>&1 > /dev/null; then \
	  pyenv local $(PYENV_NAME); \
	fi
	@PIP_FREEZE_OUT=$$(pip freeze) && \
	for dep in $(PYTHON_PACKAGES); do \
	  if ! echo "$$PIP_FREEZE_OUT" | grep $$dep 2>&1 > /dev/null; then pip install $$dep; fi; \
	done

clean:
	rm -rf downloads/

help: ## Print list of Makefile targets
	@# Taken from https://github.com/spf13/hugo/blob/master/Makefile
	@grep --with-filename -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  cut -d ":" -f2- | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' | sort

