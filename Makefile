# Made by retke for Laggrons-Dumb-Cogs

BUILD = html
SOURCE = docs
OUTPUT = docs/.build

GITHUB_TOKEN = 0
BUILD_NUMBER = 0

help:
	@echo ""
	@echo "Usage:"
	@echo "	make <command>"
	@echo ""
	@echo "Commands:"
	@echo "	reformat				Reformat all .py files being tracked by git."
	@echo "	stylecheck				Check which tracked .py files need reformatting."
	@echo "	gettext					Genereate .pot translation files with redgettext."
	@echo " upload_translations		Upload messages.pot files to crowdin."
	@echo "	compile					Compile all python files into executables."
	@echo "	docs					Compile all documentation with Sphinx into HTML files. You need to provide the destination path."
	@echo " test_docs				Run the process of sphinx, building in docs/.build and checking for all warnings.

.PHONY: docs

reformat:
	python3 -m black -l 99 `git ls-files "*.py"`

stylecheck:
	python3 -m black -l 99 --check --diff `git ls-files "*.py"`

gettext:
	redgettext --command-docstrings --verbose --recursive --exclude-files "docs/*" --exclude-files "instantcmd/*" `git ls-files "*.py"`

upload_translations:
	crowdin upload sources

download_translations:
	crowdin download	

compile:
	python3 -m compileall .

docs:
	sphinx-build -b $(BUILD) $(SOURCE) $(OUTPUT)

test_docs:
	sphinx-build -b html -W --keep-going docs docs/.build/html
