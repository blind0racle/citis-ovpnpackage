#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
import glob
import random
import string
import argparse
from pathlib import Path

import covpn_config

# -------------------------------------------------------------------
# Helper: generate a random password (12 chars, letters+digits)
# -------------------------------------------------------------------
def generate_password(length=12):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

# -------------------------------------------------------------------
# Set the system user's password (using passwd)
# -------------------------------------------------------------------
def set_system_password(username, password):
    try:
        proc = subprocess.Popen(['passwd', username], stdin=subprocess.PIPE, text=True)
        proc.communicate(input=f"{password}\n{password}\n")
        if proc.returncode != 0:
            raise Exception("passwd failed with return code {}".format(proc.returncode))
        print(f"   ✅ System password updated for {username}")
    except Exception as e:
        print(f"   ❌ Failed to set system password for {username}: {e}")
        raise

# -------------------------------------------------------------------
# Get existing IP from CCD (or assign next available)
# -------------------------------------------------------------------
def get_existing_ip(cfg, username):
    ccd_file = os.path.join(cfg['server']['ccd_dir'], username)
    if os.path.exists(ccd_file):
        with open(ccd_file, 'r') as f:
            for line in f:
                if line.startswith('ifconfig-push'):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]  # IP address
    return None

# -------------------------------------------------------------------
# Revoke and remove old certificate files
# -------------------------------------------------------------------
def revoke_and_clean_old(cfg, username):
    easyrsa_dir = cfg['server']['easyrsa_dir']
    ca_pass = cfg['server'].get('ca_password', '')
    os.chdir(easyrsa_dir)

    # 1. Revoke (if certificate exists)
    cert_path = os.path.join(easyrsa_dir, 'pki', 'issued', f'{username}.crt')
    if os.path.exists(cert_path):
        print(f"   Revoking old certificate for {username}...")
        cmd = ['./easyrsa']
        if ca_pass:
            cmd.append(f'--passin=pass:{ca_pass}')
        cmd.extend(['revoke', username])
        subprocess.run(cmd, input='yes\n', text=True, check=False)  # ignore errors if already revoked

        # (Optional) Generate new CRL – uncomment if you want to enforce revocation
        # subprocess.run(['./easyrsa', 'gen-crl'], check=True)
        # crl_src = os.path.join(easyrsa_dir, 'pki', 'crl.pem')
        # crl_dst = os.path.join(cfg['server']['keys_dir'], 'crl.pem')
        # if os.path.exists(crl_src):
        #     shutil.copy(crl_src, crl_dst)

    # 2. Remove old files from PKI
    for subdir in ['issued', 'private', 'reqs']:
        pattern = os.path.join(easyrsa_dir, 'pki', subdir, f'{username}.*')
        for f in glob.glob(pattern):
            os.remove(f)
            print(f"   Removed {f}")

# -------------------------------------------------------------------
# Build new certificate
# -------------------------------------------------------------------
def build_new_cert(cfg, username):
    easyrsa_dir = cfg['server']['easyrsa_dir']
    ca_pass = cfg['server'].get('ca_password', '')
    os.chdir(easyrsa_dir)

    print(f"   Building new certificate for {username}...")
    cmd = ['./easyrsa']
    if ca_pass:
        cmd.append(f'--passin=pass:{ca_pass}')
    cmd.extend(['build-client-full', username, 'nopass'])
    subprocess.run(cmd, input='yes\n', text=True, check=True)

# -------------------------------------------------------------------
# Write the new configuration files into the rerealise folder
# -------------------------------------------------------------------
def write_new_configs(cfg, username, password, ip_address=None):
    # Destination
    dest_dir = f"/home/administrator/rerealise/{username}"
    os.makedirs(dest_dir, exist_ok=True)

    # Copy CA and TLS keys
    keys_dir = cfg['server']['keys_dir']
    shutil.copy(os.path.join(keys_dir, 'ca.crt'), dest_dir)
    shutil.copy(os.path.join(keys_dir, 'tls.key'), dest_dir)

    # Copy new cert and key from PKI
    easyrsa_dir = cfg['server']['easyrsa_dir']
    shutil.copy(os.path.join(easyrsa_dir, 'pki', 'issued', f'{username}.crt'), dest_dir)
    shutil.copy(os.path.join(easyrsa_dir, 'pki', 'private', f'{username}.key'), dest_dir)

    # Write .ovpn
    ovpn_content = f"""client
dev tun
proto udp
remote {cfg['server']['remote_ip']} {cfg['server']['remote_port']}
resolv-retry infinite
auth-nocache
nobind
persist-key
persist-tun

cipher AES-256-GCM
data-ciphers AES-256-GCM
auth SHA256
auth-user-pass
auth-nocache

comp-lzo

ca ca.crt
cert {username}.crt
key {username}.key
tls-crypt tls.key
remote-cert-tls server
verb 3
"""
    ovpn_path = os.path.join(dest_dir, f'{username}.ovpn')
    with open(ovpn_path, 'w') as f:
        f.write(ovpn_content)

    # Write login details (данные для входа.txt)
    login_path = os.path.join(dest_dir, 'данные для входа.txt')
    with open(login_path, 'w') as f:
        f.write(f"{username}\n{password}")

    # Optionally write CCD file (if IP is provided)
    if ip_address:
        ccd_dest = os.path.join(dest_dir, f'{username}.ccd')  # just a copy, not used by server
        ccd_content = f"ifconfig-push {ip_address} {cfg['server']['vpn_netmask']}\n"
        for route in cfg['server']['routes']:
            ccd_content += f'push "route {route}"\n'
        with open(ccd_dest, 'w') as f:
            f.write(ccd_content)

    # Set ownership and permissions so administrator can access
    subprocess.check_call(['chown', '-R', 'administrator:administrator', dest_dir])
    subprocess.check_call(['chmod', '-R', '777', dest_dir])

    print(f"   ✅ Configs written to {dest_dir} with permissions")

# -------------------------------------------------------------------
# Main regeneration function
# -------------------------------------------------------------------
def regenerate_user(username, cfg, password=None, update_live=False):
    print(f"\n=== Regenerating {username} ===")

    # 1. Get existing IP (if any)
    ip = get_existing_ip(cfg, username)
    if ip:
        print(f"   Using existing IP: {ip}")
    else:
        print("   No existing IP found; will not create CCD file.")

    # 2. Revoke & clean old certs
    revoke_and_clean_old(cfg, username)

    # 3. Build new cert
    build_new_cert(cfg, username)

    # 4. Generate (or retrieve) password
    if password is None:
        password = generate_password()
    print(f"   New password: {password}")

    # 5. **CRITICAL FIX: Update the system password**
    set_system_password(username, password)

    # 6. Write new configs to rerealise
    write_new_configs(cfg, username, password, ip)

    # 7. (Optional) Update live directories
    if update_live:
        # Copy new configs to /etc/openvpn/client/<username> and /home/administrator/<username>
        client_dir = os.path.join(cfg['server']['client_dir'], username)
        admin_dir = os.path.join(cfg['server']['admin_base_dir'], username)
        # Backup old? We'll overwrite.
        os.makedirs(client_dir, exist_ok=True)
        os.makedirs(admin_dir, exist_ok=True)
        for f in ['ca.crt', 'tls.key', f'{username}.crt', f'{username}.key', f'{username}.ovpn']:
            src = os.path.join(f"/home/administrator/rerealise/{username}", f)
            if os.path.exists(src):
                shutil.copy(src, client_dir)
                shutil.copy(src, admin_dir)
        # Also copy login details
        src_login = os.path.join(f"/home/administrator/rerealise/{username}", 'данные для входа.txt')
        if os.path.exists(src_login):
            shutil.copy(src_login, admin_dir)
        # Set permissions on live directories (to match original)
        subprocess.check_call(['chown', '-R', 'administrator:administrator', admin_dir])
        subprocess.check_call(['chmod', '-R', '777', admin_dir])
        print("   ✅ Updated live directories (client and admin).")

# -------------------------------------------------------------------
# Batch entry point
# -------------------------------------------------------------------
def regenerate_batch(usernames, cfg, passwords=None, update_live=False):
    if passwords is None:
        passwords = {}
    success = []
    failed = []
    for un in usernames:
        try:
            pwd = passwords.get(un)  # if specific passwords provided
            regenerate_user(un, cfg, password=pwd, update_live=update_live)
            success.append(un)
        except Exception as e:
            print(f"❌ Failed to regenerate {un}: {e}")
            failed.append(un)
    return success, failed

# -------------------------------------------------------------------
# Command line interface (used by covpn.py)
# -------------------------------------------------------------------
def main(args):
    cfg = covpn_config.load_config(args.configpath)

    if args.batch:
        # If --batch is given as a list of usernames
        usernames = args.batch
    elif args.file:
        # If --file is given, read usernames from file (one per line)
        with open(args.file, 'r') as f:
            usernames = [line.strip() for line in f if line.strip()]
    else:
        print("Error: Please provide --batch USER1 USER2 ... or --file users.txt")
        sys.exit(1)

    # Optionally, you could supply passwords via a file or interactive
    passwords = {}
    if args.passwords_file:
        # Format: username:password per line
        with open(args.passwords_file, 'r') as f:
            for line in f:
                if ':' in line:
                    u, p = line.strip().split(':', 1)
                    passwords[u] = p

    update_live = args.update_live

    success, failed = regenerate_batch(usernames, cfg, passwords=passwords, update_live=update_live)

    print(f"\n✅ Successfully regenerated: {len(success)} users")
    if failed:
        print(f"❌ Failed: {failed}")
        sys.exit(1)
    else:
        print("All done.")

if __name__ == '__main__':
    # For standalone testing
    parser = argparse.ArgumentParser(description='Regenerate OpenVPN users')
    parser.add_argument('--batch', nargs='+', help='List of usernames')
    parser.add_argument('--file', help='File with usernames (one per line)')
    parser.add_argument('--passwords-file', help='File with username:password pairs (optional)')
    parser.add_argument('--update-live', action='store_true', help='Also update /etc/openvpn/client and /home/administrator folders')
    parser.add_argument('--configpath', help='Path to config.json')
    args = parser.parse_args()
    main(args)