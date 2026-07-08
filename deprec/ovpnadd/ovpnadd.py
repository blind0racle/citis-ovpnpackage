import os
import subprocess
import getpass
import argparse
import sys
import shutil

first_sequence = "qwertyuiop[]asdfghjkl;'\\zxcvbnm,./QWERTYUIOP{}ASDFGHJKL:\"|ZXCVBNM<>?"
second_sequence = "йцукенгшщзхъфывапролджэ\\ячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭ/ЯЧСМИТЬБЮ,"
to_russian_dict = {first_sequence[i]: second_sequence[i] for i in range(len(first_sequence))}
to_qwerty_dict = {second_sequence[i]: first_sequence[i] for i in range(len(second_sequence))}

class UserCreationError(Exception):
    """Custom exception for user creation failures."""
    pass

def root_check():
    if os.geteuid() != 0:
        print("This script must be run as root. Please run it with sudo or as root.")
        sys.exit(1)

def execute_command(command, input_data=None, check=True):
    """Run a command and return its output. If check=True, raise on error."""
    try:
        if input_data:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, text=True)
            process.communicate(input_data)
            if process.returncode != 0 and check:
                raise subprocess.CalledProcessError(process.returncode, command)
        else:
            subprocess.check_call(command)
    except subprocess.CalledProcessError as e:
        raise UserCreationError(f"Command failed: {' '.join(command)}") from e

def detect_language(text):
    if any(char in second_sequence for char in text):
        return "russian"
    elif any(char in first_sequence for char in text):
        return "qwerty"
    return "unknown"

def text_translit(text):
    language = detect_language(text)
    if language == "russian":
        return "".join(to_qwerty_dict.get(char, char) for char in text)
    elif language == "qwerty":
        return "".join(to_russian_dict.get(char, char) for char in text)
    else:
        return text

def replace_vowels(word):
    replacements = {
        'а': '4', 'А': '4',
        'о': '0', 'О': '0',
        'е': '3', 'Е': '3',
        'и': '1', 'И': '1',
        'у': '7', 'У': '7'
    }
    priority = {'о': 1, 'а': 2, 'е': 3, 'и': 4, 'у': 5}

    vowel_count = {}
    for char in word:
        if char.lower() in 'аеёиоуыэюя':
            vowel_count[char.lower()] = vowel_count.get(char.lower(), 0) + 1

    highest_priority_char = None
    highest_priority = float('inf')
    for char in vowel_count:
        if vowel_count[char] > 1 and priority[char] < highest_priority:
            highest_priority = priority[char]
            highest_priority_char = char

    result = []
    for char in word:
        if char.lower() == highest_priority_char:
            char = replacements.get(char, char)
        result.append(char)

    if result:
        result[0] = result[0].upper()
        result[-1] = result[-1].upper()

    return ''.join(result)

def get_next_ip():
    """Determine the next free IP in the 10.80.14.0/24 subnet from existing CCD files."""
    try:
        last_ip_str = subprocess.check_output(
            'grep "ifconfig-push" /etc/openvpn/server/ccd/* | awk \'{print $2}\' | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n | awk -F "." \'{print $4}\' | tail -1',
            shell=True, text=True
        ).strip()
        if last_ip_str:
            last_ip = int(last_ip_str)
        else:
            last_ip = 0
        return last_ip + 1
    except Exception:
        return 1

def cleanup_user(username):
    paths = [
        f"/etc/openvpn/client/{username}",
        f"/home/administrator/{username}",
        f"/etc/openvpn/server/ccd/{username}",
        f"/etc/easy-rsa/pki/issued/{username}.crt",
        f"/etc/easy-rsa/pki/private/{username}.key",
        f"/etc/easy-rsa/pki/reqs/{username}.req",
    ]
    for p in paths:
        if os.path.exists(p):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
            print(f"   Cleaned up: {p}")

    try:
        subprocess.check_call(['userdel', username])
        print(f"   Removed system user: {username}")
    except subprocess.CalledProcessError:
        pass

def add_user(username, password_input):
    """
    Create a new OpenVPN client user with the given password.
    Raises UserCreationError on failure, after cleaning up partial files.
    """
    password_nomorph = replace_vowels(password_input)
    final_password = text_translit(password_nomorph)

    ip_integer = get_next_ip()

    created_dirs = []
    created_files = []

    try:
        print(f"Adding user {username} ...")
        execute_command(['useradd', username])
        process = subprocess.Popen(['passwd', username], stdin=subprocess.PIPE, text=True)
        process.communicate(input=f"{final_password}\n{final_password}\n")
        if process.returncode != 0:
            raise UserCreationError(f"passwd failed for {username}")
        execute_command(['usermod', username, '-s', '/sbin/nologin'])

        print("Building client certificates ...")
        os.chdir("/etc/easy-rsa/")
        os.environ["CA_PASSWORD"] = "Dbp4ynbZ"
        execute_command(
            ['./easyrsa', '--passin=pass:{}'.format(os.environ['CA_PASSWORD']),
             'build-client-full', username, 'nopass'],
            input_data="yes"
        )

        client_dir = f"/etc/openvpn/client/{username}"
        os.makedirs(client_dir, exist_ok=True)
        created_dirs.append(client_dir)
        cert_files = [
            ('pki/issued/{}.crt'.format(username), f"{client_dir}/{username}.crt"),
            ('pki/private/{}.key'.format(username), f"{client_dir}/{username}.key"),
            ('/etc/openvpn/server/keys/ca.crt', f"{client_dir}/ca.crt"),
            ('/etc/openvpn/server/keys/tls.key', f"{client_dir}/tls.key"),
        ]
        for src, dst in cert_files:
            shutil.copy(src, dst)
            created_files.append(dst)

        ovpn_content = f"""client
dev tun
proto udp
remote 85.142.162.127 2094
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
        ovpn_file_path = f"{client_dir}/{username}.ovpn"
        with open(ovpn_file_path, 'w') as ovpn_file:
            ovpn_file.write(ovpn_content)
        created_files.append(ovpn_file_path)

        admin_dir = f"/home/administrator/{username}"
        shutil.copytree(client_dir, admin_dir)
        created_dirs.append(admin_dir)
        execute_command(['chmod', '-R', '777', admin_dir])

        login_details_path = f"{admin_dir}/данные для входа.txt"
        with open(login_details_path, 'w') as login_file:
            login_file.write(f"{username}\n{password_nomorph}")
        created_files.append(login_details_path)

        ccd_content = f"""ifconfig-push 10.80.14.{ip_integer} 255.255.255.0
push "route 10.10.11.0 255.255.255.0"
push "route 10.20.11.0 255.255.255.0"
push "route 10.40.0.0 255.255.0.0"
push "route 213.208.189.6 255.255.255.255"
push "route 213.208.189.16 255.255.255.255"
push "route 213.208.189.61 255.255.255.255"
push "route 213.208.189.62 255.255.255.255"
push "route 213.208.189.102 255.255.255.255"
push "route 213.208.189.105 255.255.255.255"
push "route 10.20.18.11 255.255.255.255"
push "route 10.20.4.2 255.255.255.255"
"""
        ccd_file_path = f"/etc/openvpn/server/ccd/{username}"
        with open(ccd_file_path, 'w') as ccd_file:
            ccd_file.write(ccd_content)
        created_files.append(ccd_file_path)

        print(f"Client {username} added and fully configured.")
        print(f"OVPN file is located at: {ovpn_file_path}")

    except Exception as e:
        print(f"\nError while creating {username}: {e}")
        print("Cleaning up partially created files...")
        cleanup_user(username)
        raise UserCreationError(f"Failed to create user {username}") from e

def main():
    root_check()
    os.environ["CA_PASSWORD"] = "Dbp4ynbZ"

    parser = argparse.ArgumentParser(
        description="Add OpenVPN client users.",
        epilog="Without arguments, runs interactively for a single user."
    )
    parser.add_argument(
        '-b', '--batch', nargs='+', metavar='USERNAME',
        help="Add multiple users in batch mode. You will be prompted for each password."
    )
    parser.add_argument(
        '-h', '--help', action='help',
        help="Show this help message and exit."
    )

    args = parser.parse_args()

    if args.batch:
        successful = []
        failed = []
        for username in args.batch:
            print(f"\n--- Setting up user: {username} ---")
            password = getpass.getpass(f"Enter password for {username}: ")
            confirm = getpass.getpass("Re-enter password: ")
            if password != confirm:
                print("Passwords do not match. Skipping this user.")
                failed.append(username)
                continue
            try:
                add_user(username, password)
                successful.append(username)
            except UserCreationError:
                failed.append(username)
                continue


        print("\n" + "=" * 50)
        print("BATCH OPERATION COMPLETED")
        print(f"Successful: {len(successful)} users: {', '.join(successful) if successful else 'None'}")
        print(f"Failed: {len(failed)} users: {', '.join(failed) if failed else 'None'}")
        print("=" * 50)
    else:
        username = input("Enter OpenVPN client username: ")
        password = getpass.getpass("Enter password for the new client: ")
        confirm = getpass.getpass("Re-enter password: ")
        if password != confirm:
            print("Passwords do not match. Exiting.")
            sys.exit(1)
        try:
            add_user(username, password)
        except UserCreationError:
            print(f"Failed to create user {username}")
            sys.exit(1)

if __name__ == "__main__":
    main()