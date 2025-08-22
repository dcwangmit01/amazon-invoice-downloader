.DEFAULT_GOAL := help
SHELL := /usr/bin/env bash

UNAME_S := $(shell uname -s)
PYTHON_VERSION := 3.12

# OSX Brew packages
BREW_PACKAGES := uv

BREW_CASKS :=

# PRE-COMMIT helpers for formatting and linting
PYTHON_FILES = $(shell find * -type f -name *.py)

.PHONY: all
all:  ## Placeholder for all targets, does nothing now
	:

.PHONY: test
test:  ## Run all tests
	uv run pytest -v --tb=short --disable-warnings --maxfail=1

.PHONY: format
format: check  ## Auto-format and check pep8

.PHONY: deps
deps: deps-os deps-dev deps-uv install-local  ## Ensure OS Dependencies (Only works for MacOS)

.PHONY: deps-os
deps-os:  ## Ensure OS Dependencies (MacOS only)
ifeq ($(UNAME_S),Darwin)
	@echo "Checking macOS dependencies..."
	@# Check if brew is installed
	@if ! which brew &> /dev/null; then \
	  echo "Homebrew is not installed. Please install it from https://brew.sh/ and try again."; \
	  exit 1; \
	fi

	@# Check brew-install dependencies
	@echo "Checking Homebrew packages: $(BREW_PACKAGES)"
	@for package in $(BREW_PACKAGES); do \
	  if brew list --versions $$package > /dev/null; then \
	    echo "$$package is already installed."; \
	  else \
	    echo "$$package is not installed. Installing via brew."; \
	    brew install $$package; \
	  fi; \
	done
	@echo "Checking Homebrew casks: $(BREW_CASKS)"
	@for cask in $(BREW_CASKS); do \
	  if brew list --cask --versions $$cask > /dev/null; then \
	    echo "$$cask is already installed."; \
	  else \
	    echo "$$cask is not installed. Installing via brew cask."; \
	    brew install --cask $$cask; \
	  fi; \
	done
else
	@echo "Unsupported operating system: $(UNAME_S). This Makefile only supports macOS. Manual dependency installation required."
	@exit 1
endif

.PHONY: deps-dev
deps-dev:  ## Ensure development dependencies
	uv run pre-commit install
	uv run pre-commit install-hooks

.PHONY: deps-uv
deps-uv:  ## Create the uv environment for Python development
	@if ! which uv &> /dev/null; then \
	  echo "uv is not installed. Please install it and try again."; \
	  exit 1; \
	fi
	@if [ ! -d .venv ]; then \
		echo "Creating uv environment in ./.venv with Python $(PYTHON_VERSION)..."; \
		uv venv -p $(PYTHON_VERSION); \
	fi
	@echo "Installing/updating dependencies with uv..."
	@uv pip install --upgrade pip
	@uv sync
	@echo "Installing Playwright browsers..."
	@uv run playwright install

.PHONY: check
check:  ## Auto-check and format via pre-commit. Re-runs automatically if files are modified.
	@uv run --active pre-commit run --all-files || (echo "pre-commit modified files. Running again..." && uv run --active pre-commit run --all-files)

.PHONY: install-local
install-local:  ## Install the program in the currently active python env
	uv pip install --editable .

.PHONY: run-local
run-local:  ## Run the program for this year
	uv run amazon-invoice-downloader --help

.PHONY: run
run:  ## Run a few examples
	uv run amazon-invoice-downloader --year 2024
	uv run amazon-invoice-downloader --date-range 20230131-20221201

.PHONY: build
build:  ## Build the project
	uv run hatch build

.PHONY: clean
clean:  ## Clean the project
	uv run hatch clean
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

.PHONY: mrclean
mrclean: clean  ## Really clean the project (except downloads)
	rm -rf .venv
	rm -f uv.lock

.PHONY: help
help:  ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
