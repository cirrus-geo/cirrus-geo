# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    +=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = src
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

#gh-pages:
#	git worktree add gh-pages gh-pages
#
#.PHONY: gh-pages-clean
#gh-pages-clean: gh-pages
#	rm -rf gh-pages/*
#
#.PHONY: gh-pages-copy
#gh-pages-copy: gh-pages-clean
#	cp -r $(BUILDDIR)/html/* gh-pages/
#
#.PHONY: gh-pages-update 
#gh-pages-update: html gh-pages-copy

.PHONY: clean
clean:
	rm -rf $(BUILDDIR)/*

symlink:
	ln -s ../src/cirrus/docs src

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile symlink
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
