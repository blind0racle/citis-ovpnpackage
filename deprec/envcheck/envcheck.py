#!/usr/bin/env python3
"""
Environment checker for OpenVPN/EasyRSA scripts.
Verifies required packages (including iptables and iptables-persistent),
directories, and symlinks.
"""

import os
import subprocess
import sys

def check_environment():
    """
    Verify all required packages, directories, and files are present.
    Returns True if all checks pass, False otherwise.
    Also prints error messages.
    """
    errors = []

    # 1. Check packages
    packages = ['openvpn', 'easy-rsa', 'iptables', 'iptables-persistent']
    for pkg in packages:
        try:
            subprocess.check_call(
                ['dpkg', '-s', pkg],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except subprocess.CalledProcessError:
            errors.append(
                f"Package '{pkg}' is not installed. Please install it with 'apt install {pkg}'."
            )

    # 2. Check directories and files (based on your tree structure)
    required_paths = [
        ('/etc/openvpn', 'dir'),
        ('/etc/openvpn/client', 'dir'),
        ('/etc/openvpn/server', 'dir'),
        ('/etc/openvpn/server/ccd', 'dir'),
        ('/etc/openvpn/server/keys', 'dir'),
        ('/etc/easy-rsa', 'dir'),
        ('/etc/easy-rsa/easyrsa', 'file_or_symlink'),
        ('/etc/easy-rsa/pki', 'dir'),
        ('/home/administrator', 'dir'),
        ('/home/archive', 'dir'),
    ]

    for path, path_type in required_paths:
        if path_type == 'dir':
            if not os.path.isdir(path):
                errors.append(f"Directory '{path}' does not exist.")
        elif path_type == 'file_or_symlink':
            if not os.path.exists(path):
                errors.append(f"File/symlink '{path}' does not exist.")

    if errors:
        print("\n❌ Environment check failed with the following errors:\n")
        for err in errors:
            print(f"  - {err}")
        print("\nPlease correct these issues and run the script again.")
        return False
    else:
        print("✅ Environment check passed.")
        return True

if __name__ == "__main__":
    success = check_environment()
    sys.exit(0 if success else 1)