.PHONY: build-CreateAnalysisFunction build-GetAnalysisFunction

build-CreateAnalysisFunction build-GetAnalysisFunction:
	mkdir -p "$(ARTIFACTS_DIR)/handlers" "$(ARTIFACTS_DIR)/services"
	cp handlers/__init__.py handlers/create_analysis.py handlers/get_analysis.py "$(ARTIFACTS_DIR)/handlers/"
	cp services/__init__.py services/dynamodb.py services/s3.py "$(ARTIFACTS_DIR)/services/"
	cp http_utils.py settings.py "$(ARTIFACTS_DIR)/"
