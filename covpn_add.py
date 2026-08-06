import os
import subprocess
import shutil
import sys
import covpn_config
from covpn_env import check_environment

class UserAddError(Exception):
    pass

first_sequence = "qwertyuiop[]asdfghjkl;'\\zxcvbnm,./QWERTYUIOP{}ASDFGHJKL:\"|ZXCVBNM<>?"
second_sequence = "йцукенгшщзхъфывапролджэ\\ячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭ/ЯЧСМИТЬБЮ,"
to_russian_dict = {first_sequence[i]: second_sequence[i] for i in range(len(first_sequence))}
to_qwerty_dict = {second_sequence[i]: first_sequence[i] for i in range(len(second_sequence))}

def detect_language(text):
    if any(char in second_sequence for char in text):
        return "russian"
    elif any(char in first_sequence for char in text):
        return "qwerty"
    return "unknown"

def text_translit(text):
    lang = detect_language(text)
    if lang == "russian":
        return "".join(to_qwerty_dict.get(char, char) for char in text)
    elif lang == "qwerty":
        return "".join(to_russian_dict.get(char, char) for char in text)
    return text

def replace_vowels(word):
    if not word:
        return ""
    replacements = {'а':'4','А':'4','о':'0','О':'0','е':'3','Е':'3','и':'1','И':'1','у':'7','У':'7'}
    priority = {'о':1,'а':2,'е':3,'и':4,'у':5}
    vowel_count = {}
    for char in word:
        if char.lower() in 'аеёиоуыэюя':
            vowel_count[char.lower()] = vowel_count.get(char.lower(), 0) + 1
    highest_priority_char = None
    highest_priority = float('inf')
    for char, cnt in vowel_count.items():
        if cnt > 1 and priority[char] < highest_priority:
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

def get_next_ip(cfg):
    ccd_dir = cfg['server']['ccd_dir']
    try:
        last_ip_str = subprocess.check_output(
            f'grep "ifconfig-push" {ccd_dir}/* | awk \'{{print $2}}\' | sort -t. -k1,1n -k2,2n -k3,3n -k4,4n | awk -F "." \'{{print $4}}\' | tail -1',
            shell=True, text=True
        ).strip()
        if last_ip_str:
            last_ip = int(last_ip_str)
        else:
            last_ip = 0
        return last_ip + 1
    except:
        return 1

def cleanup_user(username, cfg):
    paths = [
        os.path.join(cfg['server']['client_dir'], username),
        os.path.join(cfg['server']['admin_base_dir'], username),
        os.path.join(cfg['server']['ccd_dir'], username),
        os.path.join(cfg['server']['easyrsa_dir'], 'pki', 'issued', f'{username}.crt'),
        os.path.join(cfg['server']['easyrsa_dir'], 'pki', 'private', f'{username}.key'),
        os.path.join(cfg['server']['easyrsa_dir'], 'pki', 'reqs', f'{username}.req'),
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
    except:
        pass

def add_user(username, password_input, cfg):
    if password_input is None:
        password_input = ""
    password_nomorph = replace_vowels(password_input)
    final_password = text_translit(password_nomorph)
    ip_integer = get_next_ip(cfg)

    try:
        print(f"Adding user {username} ...")
        subprocess.check_call(['useradd', username])
        proc = subprocess.Popen(['passwd', username], stdin=subprocess.PIPE, text=True)
        proc.communicate(input=f"{final_password}\n{final_password}\n")
        if proc.returncode != 0:
            raise UserAddError("passwd failed")
        subprocess.check_call(['usermod', username, '-s', '/sbin/nologin'])

        os.chdir(cfg['server']['easyrsa_dir'])
        ca_pass = cfg['server'].get('ca_password', '')

        cmd = ['./easyrsa']
        if ca_pass:
            cmd.extend(['--passin', f'pass:{ca_pass}'])
        cmd.extend(['build-client-full', username, 'nopass'])
        subprocess.run(cmd, input='yes\n', text=True, check=True)

        client_dir = os.path.join(cfg['server']['client_dir'], username)
        os.makedirs(client_dir, exist_ok=True)
        shutil.copy(os.path.join('pki', 'issued', f'{username}.crt'), client_dir)
        shutil.copy(os.path.join('pki', 'private', f'{username}.key'), client_dir)
        shutil.copy(os.path.join(cfg['server']['keys_dir'], 'ca.crt'), client_dir)
        shutil.copy(os.path.join(cfg['server']['keys_dir'], 'tls.key'), client_dir)

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
        ovpn_path = os.path.join(client_dir, f'{username}.ovpn')
        with open(ovpn_path, 'w') as f:
            f.write(ovpn_content)

        admin_dir = os.path.join(cfg['server']['admin_base_dir'], username)
        shutil.copytree(client_dir, admin_dir)
        subprocess.check_call(['chmod', '-R', '777', admin_dir])

        login_path = os.path.join(admin_dir, 'данные для входа.txt')
        with open(login_path, 'w') as f:
            f.write(f"{username}\n{password_nomorph}")

        ccd_path = os.path.join(cfg['server']['ccd_dir'], username)
        ccd_content = f"ifconfig-push {cfg['server']['vpn_subnet']}.{ip_integer} {cfg['server']['vpn_netmask']}\n"
        for route in cfg['server']['routes']:
            ccd_content += f'push "route {route}"\n'
        with open(ccd_path, 'w') as f:
            f.write(ccd_content)

        print(f"Client {username} added. OVPN: {ovpn_path}")
    except Exception as e:
        print(f"Error: {e}")
        cleanup_user(username, cfg)
        raise UserAddError(f"Failed to create {username}")

def add_batch(usernames, cfg):
    success, failed = [], []
    for un in usernames:
        print(f"\n--- {un} ---")
        pw = input(f"Password for {un}: ")
        try:
            add_user(un, pw, cfg)
            success.append(un)
        except UserAddError:
            failed.append(un)
    return success, failed

def add_interactive(cfg, username=None):
    if username is None:
        username = input("Username: ").strip()
    else:
        print(f"Adding user: {username}")

    if not username:
        print("Username cannot be empty.")
        sys.exit(1)

    pw = input("Password: ")
    add_user(username, pw, cfg)