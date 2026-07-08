# covpn – OpenVPN management tool
# Installation Makefile

INSTALL_DIR = /opt/covpn
BIN_LINK = /usr/local/bin/covpn
CONFIG_DIR = /etc/covpn
CONFIG_FILE = $(CONFIG_DIR)/config.json

.PHONY: install uninstall clean help

help:
	@echo "Available targets:"
	@echo "  install   - Install covpn system-wide (requires root)"
	@echo "  uninstall - Remove covpn from system (requires root)"
	@echo "  clean     - Remove temporary files (none in this project)"
	@echo "  help      - Show this help"

install: check-root
	@echo "Installing covpn to $(INSTALL_DIR) ..."
	mkdir -p $(INSTALL_DIR)
	cp -v covpn.py covpn_config.py covpn_env.py covpn_add.py covpn_ren.py covpn_info.py $(INSTALL_DIR)/
	chmod +x $(INSTALL_DIR)/covpn.py
	ln -sf $(INSTALL_DIR)/covpn.py $(BIN_LINK)
	@echo "Symlink created: $(BIN_LINK) -> $(INSTALL_DIR)/covpn.py"

	mkdir -p $(CONFIG_DIR)
	if [ ! -f $(CONFIG_FILE) ]; then \
		if [ -f config.json.example ]; then \
			cp -v config.json.example $(CONFIG_FILE); \
			echo "Default config installed at $(CONFIG_FILE)"; \
		else \
			echo "Warning: config.json.example not found. Please create $(CONFIG_FILE) manually."; \
		fi; \
	else \
		echo "Config already exists at $(CONFIG_FILE), keeping it."; \
	fi

	@echo "Installation complete."
	@echo "You can now run: covpn --help"

uninstall: check-root
	@echo "Removing covpn..."
	rm -f $(BIN_LINK)
	rm -rf $(INSTALL_DIR)
	@echo "Note: Config file $(CONFIG_FILE) is kept."
	@echo "To remove it, delete $(CONFIG_FILE) manually."

clean:
	@echo "Nothing to clean."

check-root:
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "Please run as root (sudo)."; \
		exit 1; \
	fi