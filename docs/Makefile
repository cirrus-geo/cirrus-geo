HTTP_PORT= 8000
STAGEDIR = _src
BUILDDIR = _build
CONFFILE = src/conf.py
INCLUDE  = src/index.include
CIRRUS_VERSION ?= $(shell git rev-parse --abbrev-ref HEAD) 

gh-pages:
	git worktree add gh-pages gh-pages

gh-pages/.nojekyll: gh-pages
	touch $@

gh-pages/index.html: gh-pages/.nojekyll src/index.html
	cp src/index.html $@

gh-pages/$(CIRRUS_VERSION):
	mkdir $@

.PHONY: gh-pages-clean
gh-pages-clean:
	rm -rf gh-pages/$(CIRRUS_VERSION)

.PHONY: gh-pages-copy
gh-pages-copy: gh-pages-clean gh-pages/$(CIRRUS_VERSION)
	cp -r $(BUILDDIR)/html/* gh-pages/$(CIRRUS_VERSION)

.PHONY:
gh-pages-versions-update: gh-pages
	python3 update-versions.py gh-pages

.PHONY: gh-pages-update
gh-pages-update: clean build gh-pages/index.html gh-pages-copy gh-pages-versions-update

.PHONY: clean
clean:
	cirrus docs clean \
		--staging-dir $(STAGEDIR) \
		--output-dir $(BUILDDIR) \


.PHONY: stage
stage:
	cirrus docs stage \
		--staging-dir $(STAGEDIR) \
		--conf-file $(CONFFILE) \
		--custom-index-include $(INCLUDE) \
		--exclude-project-docs \
		--exclude-lib-docs \
		--exclude-plugin-docs \


.PHONY: build
build: stage
	cirrus docs build \
		--staging-dir $(STAGEDIR) \
		--output-dir $(BUILDDIR) \


.PHONY: serve
serve: gh-pages
	python -m http.server $(HTTP_PORT) -d gh-pages 
