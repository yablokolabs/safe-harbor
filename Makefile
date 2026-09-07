# Safe Harbor — Yabloko Labs
#
# Gen1 build tooling. Everything here runs on the CONNECTED ACQUISITION
# machine (Debian build host). Nothing here modifies the deployment target.

SHELL := /bin/bash
VERSION := 0.1.0
ARCH := amd64
BUNDLE := dist/safe-harbor-gen1-$(VERSION)-$(ARCH).tar.gz

.PHONY: all acquire verify bundle test check clean

all: test bundle

## acquire — download and verify every pinned upstream artifact (needs network)
acquire:
	./acquisition/acquire.sh

## verify — re-verify every acquired artifact against the lock manifest
verify:
	./acquisition/verify.sh

## bundle — assemble the verified offline bundle and hash it
bundle: $(BUNDLE)

$(BUNDLE): acquisition/acquire.sh acquisition/verify.sh
	./acquisition/acquire.sh --if-missing
	./acquisition/verify.sh --strict
	./acquisition/assemble.sh
	@echo
	@echo "Offline bundle:"
	@ls -lh dist/safe-harbor-gen1-$(VERSION)-$(ARCH).tar.gz
	@echo "SHA-256:"
	@sha256sum dist/safe-harbor-gen1-$(VERSION)-$(ARCH).tar.gz

## test — run the local pytest suite (safe on any machine)
test:
	python3 -m pytest tests/

## check — static checks that are safe to run locally
check:
	@echo "== bash syntax =="
	@for f in acquisition/*.sh deploy/*.sh scripts/*.sh; do \
		bash -n "$$f" && echo "OK  $$f" || exit 1; \
	done
	@echo "== python compile =="
	@python3 -m compileall -q safeharbor tests && echo "OK"
	@if command -v shellcheck >/dev/null 2>&1; then \
		echo "== shellcheck =="; \
		shellcheck acquisition/*.sh deploy/*.sh scripts/*.sh; \
	else \
		echo "shellcheck not installed — skipped (bash -n passed)"; \
	fi

clean:
	rm -rf dist build safeharbor.egg-info .pytest_cache upstream-work
	rm -rf acquisition/cache