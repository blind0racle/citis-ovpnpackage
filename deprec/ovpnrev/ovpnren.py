#!/usr/bin/env python3

import os
import subprocess
import shutil
import argparse
import sys
import datetime
import glob
import re

def root_check():
    if os.geteuid() != 0:
        print("This script must be run as root. Please run it with sudo or as root.")
        sys.exit(1)

def execute_command(command, input_data=None):
    try:
        if input_data:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, text=True)
            process.communicate(input_data)
        else:
            subprocess.check_call(command)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        sys.exit(1)

def get_cert_expiry(cert_path):
    """Return datetime object of the certificate's notAfter date, or None on error."""
    try:
        output = subprocess.check_output(
            ['openssl', 'x509', '-enddate', '-noout', '-in', cert_path],
            text=True
        ).strip()
        match = re.search(r'notAfter=(.*)', output)
        if not match:
            return None
        date_str = match.group(1).strip()
        parts = date_str.split()
        month = parts[0]
        day = parts[1].strip()
        time = parts[2]
        year = parts[3]
        dt_str = f"{month} {day} {time} {year}"
        return datetime.datetime.strptime(dt_str, "%b %d %H:%M:%S %Y")
    except Exception as e:
        print(f"Error reading expiry from {cert_path}: {e}")
        return None

def get_all_cert_expiries():
    cert_dir = "/etc/easy-rsa/pki/issued"
    cert_files = glob.glob(os.path.join(cert_dir, "*.crt"))
    result = {}
    for cert_path in cert_files:
        username = os.path.splitext(os.path.basename(cert_path))[0]
        expiry = get_cert_expiry(cert_path)
        if expiry:
            result[username] = expiry
    return result

def revoke_renew_user(username):
    client_dir = f"/etc/openvpn/client/{username}"
    admin_dir = f"/home/administrator/{username}"

    print(f"\nStarting certificate renewal for {username}...")
    print("=" * 50)

    # --- PRESERVE LOGIN DETAILS ---
    login_file = os.path.join(admin_dir, "данные для входа.txt")
    login_content = None
    if os.path.exists(login_file):
        with open(login_file, 'r') as f:
            login_content = f.read()
        print("   Preserved login details.")
    else:
        print("   Warning: No login file found; it will not be restored.")

    os.chdir("/etc/easy-rsa/")

    # 1. Revoke old certificate
    print("1. Revoking old certificate...")
    execute_command(['./easyrsa', '--passin=pass:Dbp4ynbZ', 'revoke', username], "yes")

    # 2. Generate CRL
    print("2. Generating CRL...")
    execute_command(['./easyrsa', 'gen-crl'])

    # 3. Copy CRL
    if os.path.exists("pki/crl.pem"):
        shutil.copy("pki/crl.pem", "/etc/openvpn/server/keys/crl.pem")
        print("3. CRL copied to OpenVPN server directory")

    # 4. Delete old files
    print("4. Deleting old certificate files...")
    files_to_delete = [
        f"pki/reqs/{username}.req",
        f"pki/private/{username}.key",
        f"pki/issued/{username}.crt",
        f"{client_dir}/{username}.crt",
        f"{client_dir}/{username}.key",
    ]
    for file_path in files_to_delete:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"   Deleted: {file_path}")

    # 5. Generate new certificate
    print("5. Generating new certificate...")
    subprocess.check_call(['bash', '-c', 'export CA_PASSWORD="Dbp4ynbZ"'])
    execute_command(
        ['./easyrsa', '--passin=pass:Dbp4ynbZ', 'build-client-full', username, 'nopass'],
        input_data="yes"
    )

    # 6. Copy new certificate to client directory
    print("6. Copying new certificate...")
    os.makedirs(client_dir, exist_ok=True)
    shutil.copy(f"pki/issued/{username}.crt", f"{client_dir}/{username}.crt")
    shutil.copy(f"pki/private/{username}.key", f"{client_dir}/{username}.key")

    # 7. Copy all files to administrator directory (preserve login)
    print("7. Copying files to administrator directory...")
    os.makedirs(admin_dir, exist_ok=True)

    # Clear admin dir (but we already saved login)
    if os.listdir(admin_dir):
        execute_command(['rm', '-rf', f"{admin_dir}/*"])
        print(f"   Cleared {admin_dir}/*")

    # Copy new cert files from client_dir
    for item in os.listdir(client_dir):
        src = os.path.join(client_dir, item)
        dst = os.path.join(admin_dir, item)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"   Copied: {item}")

    # Restore login file if it existed
    if login_content is not None:
        login_file_path = os.path.join(admin_dir, "данные для входа.txt")
        with open(login_file_path, 'w') as f:
            f.write(login_content)
        print(f"   Restored login details: {login_file_path}")

    # Set permissions
    execute_command(['chown', '-R', 'administrator:administrator', admin_dir])
    execute_command(['chmod', '-R', '777', admin_dir])
    print(f"   Set permissions on administrator directory")

    # 8. Restart OpenVPN
    print("8. Restarting OpenVPN service...")
    execute_command(['systemctl', 'restart', 'openvpn@server'])

    print("\n" + "=" * 50)
    print(f"✓ Certificate successfully renewed for: {username}")
    print(f"  New certificate: {client_dir}/{username}.crt")
    print(f"  New key: {client_dir}/{username}.key")
    print(f"  Administrator directory: {admin_dir} (login details preserved)")

def list_users(option):
    now = datetime.datetime.utcnow()
    expiries = get_all_cert_expiries()
    if not expiries:
        print("No client certificates found.")
        return

    user_list = []
    for user, expiry in expiries.items():
        days = (expiry - now).days
        user_list.append((user, expiry, days))

    if option == 'w':
        filtered = [(u, e, d) for u, e, d in user_list if 0 <= d <= 7]
        title = "Users expiring within 7 days"
    elif option == 'm':
        filtered = [(u, e, d) for u, e, d in user_list if 0 <= d <= 30]
        title = "Users expiring within 30 days"
    elif option == 'q':
        filtered = [(u, e, d) for u, e, d in user_list if 0 <= d <= 120]
        title = "Users expiring within 120 days"
    elif option == 'cl10':
        sorted_list = sorted(user_list, key=lambda x: x[2])
        filtered = [(u, e, d) for u, e, d in sorted_list if d >= 0][:10]
        title = "10 closest expirations"
    elif option == 'cl25':
        sorted_list = sorted(user_list, key=lambda x: x[2])
        filtered = [(u, e, d) for u, e, d in sorted_list if d >= 0][:25]
        title = "25 closest expirations"
    else:
        print(f"Invalid list option: {option}")
        print("Valid options: w, m, q, cl10, cl25")
        return

    if not filtered:
        print("No users match the criteria.")
        return

    print(f"\n{title}:")
    print("-" * 60)
    print(f"{'Username':<20} {'Expiry Date':<25} {'Days Left'}")
    print("-" * 60)
    for user, expiry, days in filtered:
        print(f"{user:<20} {expiry.strftime('%Y-%m-%d %H:%M:%S'):<25} {days}")
    print("-" * 60)

def main():
    root_check()

    parser = argparse.ArgumentParser(
        description="Revoke and renew OpenVPN client certificates, or list expiring ones.",
        epilog="Without arguments, runs interactively for a single user."
    )
    parser.add_argument(
        '-b', '--batch', nargs='+', metavar='USERNAME',
        help="Revoke and renew multiple users in batch mode (no confirmation)."
    )
    parser.add_argument(
        '-l', '--list', choices=['w', 'm', 'q', 'cl10', 'cl25'],
        help="List users whose certificates expire soon. Options: w(7d), m(30d), q(120d), cl10(10 closest), cl25(25 closest)."
    )
    parser.add_argument(
        '-h', '--help', action='help',
        help="Show this help message and exit."
    )

    args = parser.parse_args()

    if args.list:
        list_users(args.list)
        return

    if args.batch:
        for username in args.batch:
            revoke_renew_user(username)
        print("\nAll specified users processed.")
        return

    # Interactive mode (original)
    username = input("Enter OpenVPN client username: ").strip()
    if not username:
        print("Error: Username cannot be empty")
        sys.exit(1)

    print(f"\nWARNING: This will revoke and renew the certificate for user: {username}")
    response = input("Are you sure you want to continue? (yes/NO): ")
    if response.lower() != 'yes':
        print("Operation cancelled.")
        return

    revoke_renew_user(username)

if __name__ == "__main__":
    main()