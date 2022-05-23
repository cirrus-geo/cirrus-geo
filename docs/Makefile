BUILDDIR = _build
VERSION ?= $(shell git rev-parse --abbrev-ref HEAD) 

gh-pages:
	git worktree add gh-pages gh-pages

gh-pages/index.html: gh-pages
	cat > gh-pages/index.html <<"EOF"
	<!DOCTYPE html>
	<html>
	  <head>
		<title>Redirecting to latest stable version docs</title>
		<meta charset="utf-8">
		<meta http-equiv="refresh" content="0; url=./stable/index.html">
	  </head>
	</html>
	EOF

gh-pages/$(VERSION): gh-pages
	mkdir gh-pages/$(VERSION)

.PHONY: gh-pages-clean
gh-pages-clean: gh-pages/$(VERSION)
	rm -rf gh-pages/$(VERSION)*

.PHONY: gh-pages-copy
gh-pages-copy: gh-pages-clean
	cp -r $(BUILDDIR)/html/* gh-pages/$(VERSION)

.PHONY: gh-pages-update
gh-pages-update: clean build gh-pages-copy gh-pages/index.html
	# TODO: script to update latest and stable links in gh-pages
	# TODO: also need to update versions for the list in the theme

.PHONY: clean
clean:
	cirrus docs clean

.PHONY: stage
stage:
	cirrus docs stage \
		--staging-dir ./_src \
		--conf-file ./conf.py \
		--exclude-project-docs \
		--exclude-lib-docs \
		--exclude-plugin-docs \


.PHONY: build
build: stage
	cirrus docs build \
		--staging-dir ./_src \
		--output-dir ./_build \

