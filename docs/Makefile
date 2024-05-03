HTTP_PORT= 8000
STAGEDIR = src
BUILDDIR = build
CONFFILE = src/conf.py
INCLUDE  = src/index.include
export CIRRUS_VERSION := $(or $(CIRRUS_VERSION),$(shell git rev-parse --abbrev-ref HEAD))

gh-pages:
	git worktree add gh-pages gh-pages

gh-pages/.nojekyll: gh-pages
	touch $@

gh-pages/$(CIRRUS_VERSION): gh-pages
	mkdir -p $@

.PHONY: gh-pages-clean
gh-pages-clean:
	rm -rf gh-pages/$(CIRRUS_VERSION)

.PHONY: gh-pages-copy
gh-pages-copy: gh-pages-clean gh-pages/$(CIRRUS_VERSION)
	cp -r $(BUILDDIR)/html/* gh-pages/$(CIRRUS_VERSION)

.PHONY:
gh-pages-versions-update: gh-pages/.nojekyll
	python3 update-versions.py gh-pages

.PHONY: gh-pages-update
gh-pages-update: clean build gh-pages-copy gh-pages-versions-update

.PHONY: clean
clean:
	rm -rf $(BUILDDIR)/*

.PHONY: build
build: clean
	sphinx-build -M html $(STAGEDIR) $(BUILDDIR)

.PHONY: serve
serve: gh-pages
	python -m http.server $(HTTP_PORT) -d gh-pages
