# Herdr + Mistral Vibe Integration Makefile
# ========================================
#
# Usage:
#   make help              - Show all available targets
#   make install           - Install integration to ~/.vibe/
#   make uninstall         - Remove integration
#   make build             - Build TypeScript adapter
#   make test              - Run integration tests
#
# Environment Variables:
#   HERDR_VIBE_DEBUG=1     - Enable debug logging in hook script
#   HERDR_SOCKET_PATH      - Override Herdr socket path for testing

# Project configuration
PROJECT_ROOT := $(shell dirname $(abspath $(lastword $(MAKEFILE_LIST))))
ADAPTER_DIR := $(PROJECT_ROOT)/adapter
DIST_DIR := $(ADAPTER_DIR)/dist
SCRIPTS_DIR := $(PROJECT_ROOT)/scripts

# Files to install
INSTALL_FILES := \
	$(ADAPTER_DIR)/herdr-agent-state.py \
	$(ADAPTER_DIR)/hooks.toml

# Targets

.PHONY: help
help: ## Show this help message
	@echo "Herdr + Mistral Vibe Integration"
	@echo "================================"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

.PHONY: build
build: ## Build TypeScript adapter
	@echo "Building TypeScript adapter..."
	cd $(ADAPTER_DIR) && npm run build
	@echo "Done"

.PHONY: typecheck
typecheck: ## Run TypeScript type checking
	@echo "Running type check..."
	cd $(ADAPTER_DIR) && pnpm run typecheck
	@echo "Done"

.PHONY: lint
lint: typecheck ## Run linting and type checking

.PHONY: install
install: build ## Install integration to ~/.vibe/
	@echo "Installing Herdr + Mistral Vibe integration..."
	python3 $(ADAPTER_DIR)/install.py
	@echo "Done"

.PHONY: uninstall
uninstall: ## Uninstall integration from ~/.vibe/
	@echo "Uninstalling Herdr + Mistral Vibe integration..."
	python3 $(ADAPTER_DIR)/install.py --uninstall
	@echo "Done"

.PHONY: reinstall
reinstall: uninstall install ## Reinstall integration (clean install)

.PHONY: dev
dev: build install ## Build and install for development

.PHONY: test
test: build ## Run integration tests
	@echo "Running integration tests..."
	python3 $(SCRIPTS_DIR)/test-integration.py

.PHONY: test-all
test-all: build ## Run all tests (unit + integration)
	@echo "Running unit tests..."
	cd $(ADAPTER_DIR) && pnpm test
	@echo "Running integration tests..."
	python3 $(SCRIPTS_DIR)/test-integration.py

.PHONY: test-unit
test-unit: build ## Run unit tests only
	@echo "Running unit tests..."
	cd $(ADAPTER_DIR) && pnpm test

.PHONY: test-debug
test-debug: ## Run tests with debug output
	@echo "Running tests with debug output..."
	python3 $(SCRIPTS_DIR)/test-integration.py --debug

.PHONY: test-with-herdr
test-with-herdr: ## Run tests with real Herdr instance
	@echo "Running tests with real Herdr..."
	python3 $(SCRIPTS_DIR)/test-integration.py --real-herdr

.PHONY: clean
clean: ## Clean build artifacts
	@echo "Cleaning build artifacts..."
	cd $(ADAPTER_DIR) && rm -rf $(DIST_DIR)
	@echo "Done"

.PHONY: clean-all
clean-all: clean ## Clean all build artifacts and node_modules
	@echo "Cleaning all build artifacts and dependencies..."
	cd $(ADAPTER_DIR) && rm -rf $(DIST_DIR) node_modules
	@echo "Done"

.PHONY: deps
deps: ## Install Node.js dependencies
	@echo "Installing dependencies..."
	cd $(ADAPTER_DIR) && npm install
	@echo "Done"

.PHONY: check
check: build test ## Build and test everything

.PHONY: verify
verify: install ## Install and verify integration

.PHONY: run
run: build ## Run vibe-herdr (for testing outside Herdr)
	@echo "Running vibe-herdr..."
	node $(DIST_DIR)/index.js

.PHONY: doctor
doctor: ## Check system and project health
	@echo "=== Herdr-Vibe Integration Doctor ==="
	@echo ""
	@echo "Node.js version:"
	@node --version 2>&1 || echo "  Node.js not found"
	@echo ""
	@echo "npm version:"
	@npm --version 2>&1 || echo "  npm not found"
	@echo ""
	@echo "Python version:"
	@python3 --version 2>&1 || echo "  Python not found"
	@echo ""
	@echo "Herdr installed:"
	@command -v herdr >/dev/null 2>&1 && echo "  herdr found at $(which herdr)" || echo "  herdr not found"
	@echo ""
	@echo "vibe installed:"
	@command -v vibe >/dev/null 2>&1 && echo "  vibe found at $(which vibe)" || echo "  vibe not found"
	@echo ""
	@echo "vibe-herdr installed:"
	@command -v vibe-herdr >/dev/null 2>&1 && echo "  vibe-herdr found at $(which vibe-herdr)" || echo "  vibe-herdr not found"
	@echo ""
	@echo "Integration files:"
	@for file in ~/.vibe/herdr-agent-state.py ~/.vibe/hooks.toml; do \
		if [ -f "$$file" ]; then \
			echo "  $$file exists"; \
		else \
			echo "  $$file NOT FOUND"; \
		fi; \
	done
	@echo ""

.PHONY: test-hook
test-hook: ## Test hook script manually
	@echo "Testing POST_AGENT hook..."
	echo '{"hook_event_name": "POST_AGENT", "session_id": "test-123"}' \
		| HERDR_PANE_ID=test:w1:p1 HERDR_SOCKET_PATH=/tmp/test-herdr.sock \
		python3 $(ADAPTER_DIR)/herdr-agent-state.py
	@echo "Done"

.PHONY: test-socket-server
test-socket-server: ## Start test socket server
	@echo "Starting test socket server..."
	@echo "Press Ctrl+C to stop"
	python3 $(SCRIPTS_DIR)/test-socket-server.py

.PHONY: herdr-env
herdr-env: ## Show Herdr environment variables
	@python3 $(SCRIPTS_DIR)/herdr-client.py env

.PHONY: socket-path
socket-path: ## Show current Herdr socket path
	@python3 $(SCRIPTS_DIR)/herdr-client.py env 2>&1 | grep HERDR_SOCKET_PATH || echo "Herdr not running"

.PHONY: logs
logs: ## Show Herdr logs (for debugging)
	@echo "Herdr Server Log (last 50 lines):"
	@tail -50 ~/.config/herdr/herdr-server.log 2>/dev/null || echo "  Not found"
	@echo ""
	@echo "Herdr Client Log (last 50 lines):"
	@tail -50 ~/.config/herdr/herdr-client.log 2>/dev/null || echo "  Not found"

.PHONY: quickstart
quickstart: deps build install ## Quick setup for development
	@echo "Quickstart complete!"

.PHONY: env
env: ## Show project environment
	@echo "Herdr-Vibe Integration Environment"
	@echo "=================================="
	@echo ""
	@echo "Project Root: $(PROJECT_ROOT)"
	@echo "Adapter Dir: $(ADAPTER_DIR)"
	@echo "Dist Dir: $(DIST_DIR)"

.PHONY: reset
reset: clean clean-all ## Reset project (clean all build artifacts)

.PHONY: default
default: help ## Default target - show help

# mise targets
.META.PHONY: mise-install
mise-install: ## Install tools via mise
	@echo "Installing tools via mise..."
	mise install
	@echo "Done"

.META.PHONY: mise-env
mise-env: ## Setup mise environment
	@echo "Setting up mise environment..."
	mise use --global node@20.17.0
	mise use --global pnpm@11.24.0
	mise use --global python@3.11.11
	mise plugin install node
	mise plugin install python
	@echo "Done"

# mise-based full setup
.META.PHONY: mise-setup
mise-setup: mise-env mise-install ## Full mise setup
	@echo "Running pnpm install..."
	pnpm install -r
	@echo "Installing lefthook..."
	pnpm add -D lefthook@2.1.12
	npx lefthook install
	@echo "Setup complete!"

# File dependencies
$(DIST_DIR)/index.js:
	cd $(ADAPTER_DIR) && npm run build

build: $(DIST_DIR)/index.js
