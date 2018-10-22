# Made by retke for Laggrons-Dumb-Cogs

BUILD = html
SOURCE = docs
OUTPUT = docs/_build

GITHUB_TOKEN = 0
BUILD_NUMBER = 0

help:
	@echo ""
	@echo "Usage:"
	@echo "	make <command>"
	@echo ""
	@echo "Commands:"
	@echo "	reformat		Reformat all .py files being tracked by git."
	@echo "	stylecheck		Check which tracked .py files need reformatting."
	@echo "	gettext			Genereate .pot translation files with redgettext."
	@echo "	compile			Compile all python files into executables."
	@echo "	docs			Compile all documentation with Sphinx into HTML files. You need to provide the destination path."

.PHONY: docs

reformat:
	@echo "Starting..."
	@python3 -m black -l 99 --skip-numeric-underscore-normalization `git ls-files "*.py"`

stylecheck:
	@echo "Starting..."
	@python3 -m black -l 99 --skip-numeric-underscore-normalization --check --diff `git ls-files "*.py"`

gettext:
	@echo "Starting..."
	@redgettext --command-docstrings --verbose --recursive . --exclude-files "info_deploy.py"
	@echo "Done!"

compile:
	@echo "Starting..."
	@python3 -m compileall .
	@echo "Done!"

deploy:
	@python3 info_deploy.py $(GITHUB_TOKEN) $(BUILD_NUMBER)

docs:
	@python3 -m sphinx -b $(BUILD) $(SOURCE) $(OUTPUT)
