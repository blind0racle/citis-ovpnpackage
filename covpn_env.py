import os
import subprocess
import sys
import shutil
import covpn_config

def check_environment(fix=False):
    cfg = covpn_config.get_config()
    errors = []

    # Packages
    packages = ['openvpn', 'easy-rsa', 'iptables', 'iptables-persistent']
    for pkg in packages:
        try:
            subprocess.check_call(['dpkg', '-s', pkg],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        except:
            errors.append(f"Package '{pkg}'")

    # Directories
    dirs = [
        cfg['server']['openvpn_dir'],
        cfg['server']['client_dir'],
        cfg['server']['ccd_dir'],
        cfg['server']['keys_dir'],
        cfg['server']['easyrsa_dir'],
        cfg['server']['admin_base_dir'],
        cfg['server']['archive_base_dir'],
    ]
    for d in dirs:
        if not os.path.isdir(d):
            errors.append(f"Directory '{d}'")

    # EasyRSA symlink
    if not os.path.exists(os.path.join(cfg['server']['easyrsa_dir'], 'easyrsa')):
        errors.append("EasyRSA 'easyrsa' symlink")

    if not errors:
        print("✅ Environment check passed.")
        return True

    print("❌ Missing items:")
    for e in errors:
        print(f"  - {e}")

    if not fix:
        print("\nUse --fix to automatically resolve.")
        return False

    # --- FIX ---
    print("\n🔧 Attempting fixes...")

    # 1. Install missing packages
    for pkg in packages:
        if any(pkg in e for e in errors):
            print(f"📦 Installing {pkg}...")
            subprocess.check_call(['apt-get', 'update'])
            subprocess.check_call(['apt-get', 'install', '-y', pkg])

    # 2. Create missing directories
    for d in dirs:
        if any(d in e for e in errors):
            os.makedirs(d, exist_ok=True)
            print(f"📁 Created {d}")

    # 3. Set up EasyRSA if needed
    easyrsa_dir = cfg['server']['easyrsa_dir']
    if not os.path.exists(os.path.join(easyrsa_dir, 'easyrsa')):
        if os.path.exists(easyrsa_dir):
            shutil.rmtree(easyrsa_dir)
        subprocess.check_call(['make-cadir', easyrsa_dir])
        print(f"✅ EasyRSA initialized at {easyrsa_dir}")

    # Re‑check
    print("\nRe‑checking environment...")
    return check_environment(fix=False)