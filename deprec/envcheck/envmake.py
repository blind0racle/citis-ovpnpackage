#!/usr/bin/env python3
"""
OpenVPN/EasyRSA environment setup script.
Installs packages (openvpn, easy-rsa, iptables, iptables-persistent),
creates directories, initializes EasyRSA.
Idempotent – safe to run multiple times.
"""

import os
import subprocess
import sys
import shutil

def root_check():
    if os.geteuid() != 0:
        print("This script must be run as root. Please run it with sudo or as root.")
        sys.exit(1)

def run_command(command, check=True, capture=False):
    """Run a shell command. Returns (returncode, stdout, stderr)."""
    try:
        if capture:
            result = subprocess.run(command, shell=True, check=check,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True)
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        else:
            subprocess.check_call(command, shell=True)
            return 0, "", ""
    except subprocess.CalledProcessError as e:
        if check:
            print(f"Command failed: {command}")
            print(f"Error: {e}")
            sys.exit(1)
        return e.returncode, "", str(e)

def is_package_installed(pkg):
    """Check if a package is installed via dpkg."""
    rc, _, _ = run_command(f"dpkg -s {pkg}", check=False, capture=True)
    return rc == 0

def install_package(pkg):
    """Install a package using apt-get if not already installed."""
    if is_package_installed(pkg):
        print(f"✅ Package '{pkg}' is already installed.")
        return True
    print(f"📦 Installing '{pkg}'...")
    rc, _, _ = run_command(f"apt-get update && apt-get install -y {pkg}", check=False, capture=True)
    if rc != 0:
        print(f"❌ Failed to install '{pkg}'. Please check your network and package manager.")
        return False
    print(f"✅ Package '{pkg}' installed successfully.")
    return True

def ensure_directory(path):
    """Create a directory if it doesn't exist. Return True if created or already exists."""
    if os.path.exists(path):
        if os.path.isdir(path):
            print(f"✅ Directory '{path}' already exists.")
            return True
        else:
            print(f"❌ '{path}' exists but is not a directory. Please remove it and try again.")
            return False
    try:
        os.makedirs(path, exist_ok=True)
        print(f"📁 Created directory: {path}")
        return True
    except Exception as e:
        print(f"❌ Failed to create '{path}': {e}")
        return False

def setup_easyrsa():
    """Initialize EasyRSA using make-cadir if /etc/easy-rsa doesn't exist."""
    easyrsa_dir = "/etc/easy-rsa"
    if os.path.exists(easyrsa_dir):
        if os.path.isdir(easyrsa_dir) and os.path.exists(os.path.join(easyrsa_dir, "easyrsa")):
            print(f"✅ EasyRSA already set up at {easyrsa_dir}")
            return True
        else:
            print(f"⚠️  '{easyrsa_dir}' exists but is incomplete. Removing and recreating...")
            try:
                shutil.rmtree(easyrsa_dir)
            except Exception as e:
                print(f"❌ Failed to remove old directory: {e}")
                return False

    # Check if make-cadir is available
    if shutil.which("make-cadir") is None:
        print("❌ 'make-cadir' command not found. Please install easy-rsa package.")
        return False

    # Create directory using make-cadir
    try:
        subprocess.check_call(["make-cadir", easyrsa_dir])
        print(f"✅ EasyRSA initialized at {easyrsa_dir}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to run make-cadir: {e}")
        return False

def main():
    root_check()

    print("=" * 60)
    print("OpenVPN/EasyRSA Environment Setup")
    print("=" * 60)

    # 1. Install packages (including iptables and iptables-persistent)
    packages = ["openvpn", "easy-rsa", "iptables", "iptables-persistent"]
    all_ok = True
    for pkg in packages:
        if not install_package(pkg):
            all_ok = False

    if not all_ok:
        print("\n❌ Some packages failed to install. Aborting.")
        sys.exit(1)

    # 2. Create directories
    directories = [
        "/etc/openvpn",
        "/etc/openvpn/client",
        "/etc/openvpn/server",
        "/etc/openvpn/server/ccd",
        "/etc/openvpn/server/keys",
        "/home/administrator",
        "/home/archive",
    ]
    for d in directories:
        if not ensure_directory(d):
            all_ok = False

    if not all_ok:
        print("\n❌ Some directories could not be created. Aborting.")
        sys.exit(1)

    # 3. Set up EasyRSA
    if not setup_easyrsa():
        print("\n❌ EasyRSA setup failed. Aborting.")
        sys.exit(1)

    # 4. Final message
    print("\n" + "=" * 60)
    print("✅ Environment setup completed successfully.")
    print("   - Packages installed: openvpn, easy-rsa, iptables, iptables-persistent")
    print("   - Directories created under /etc/openvpn, /home/administrator, /home/archive")
    print("   - EasyRSA initialized at /etc/easy-rsa")
    print("=" * 60)

if __name__ == "__main__":
    main()