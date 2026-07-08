import os
import subprocess
import shutil
import datetime
import glob
import re
import covpn_config

def get_cert_expiry(cert_path):
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
    except:
        return None

def get_all_cert_expiries(cfg):
    cert_dir = os.path.join(cfg['server']['easyrsa_dir'], 'pki', 'issued')
    cert_files = glob.glob(os.path.join(cert_dir, '*.crt'))
    result = {}
    for path in cert_files:
        un = os.path.splitext(os.path.basename(path))[0]
        exp = get_cert_expiry(path)
        if exp:
            result[un] = exp
    return result

def revoke_renew_user(username, cfg):
    client_dir = os.path.join(cfg['server']['client_dir'], username)
    admin_dir = os.path.join(cfg['server']['admin_base_dir'], username)

    login_path = os.path.join(admin_dir, 'данные для входа.txt')
    login_content = None
    if os.path.exists(login_path):
        with open(login_path, 'r') as f:
            login_content = f.read()
        print("   Preserved login details.")
    else:
        print("   Warning: No login file found.")

    os.chdir(cfg['server']['easyrsa_dir'])
    ca_pass = cfg['server']['ca_password']

    subprocess.run(['./easyrsa', f'--passin=pass:{ca_pass}', 'revoke', username],
                   input='yes\n', text=True, check=True)
    subprocess.run(['./easyrsa', 'gen-crl'], check=True)
    if os.path.exists('pki/crl.pem'):
        shutil.copy('pki/crl.pem', os.path.join(cfg['server']['keys_dir'], 'crl.pem'))

    for f in ['pki/reqs', 'pki/private', 'pki/issued']:
        p = os.path.join(f, f'{username}.*')
        for file in glob.glob(p):
            os.remove(file)
    for f in [f'{username}.crt', f'{username}.key']:
        p = os.path.join(client_dir, f)
        if os.path.exists(p):
            os.remove(p)

    subprocess.run(['./easyrsa', f'--passin=pass:{ca_pass}', 'build-client-full', username, 'nopass'],
                   input='yes\n', text=True, check=True)

    os.makedirs(client_dir, exist_ok=True)
    shutil.copy(os.path.join('pki', 'issued', f'{username}.crt'), client_dir)
    shutil.copy(os.path.join('pki', 'private', f'{username}.key'), client_dir)

    if os.path.exists(admin_dir):
        shutil.rmtree(admin_dir)
    os.makedirs(admin_dir, exist_ok=True)
    for item in os.listdir(client_dir):
        src = os.path.join(client_dir, item)
        if os.path.isfile(src):
            shutil.copy2(src, admin_dir)
    if login_content is not None:
        with open(os.path.join(admin_dir, 'данные для входа.txt'), 'w') as f:
            f.write(login_content)
    subprocess.check_call(['chown', '-R', 'administrator:administrator', admin_dir])
    subprocess.check_call(['chmod', '-R', '777', admin_dir])
    subprocess.check_call(['systemctl', 'restart', 'openvpn@server'])
    print(f"✓ Renewed {username}")

def list_expirations(option, cfg):
    expiries = get_all_cert_expiries(cfg)
    now = datetime.datetime.utcnow()
    items = [(u, (exp-now).days) for u, exp in expiries.items()]
    filtered = []
    if option == 'w':
        filtered = [(u,d) for u,d in items if 0 <= d <= 7]
        title = "expiring in ≤7 days"
    elif option == 'm':
        filtered = [(u,d) for u,d in items if 0 <= d <= 30]
        title = "expiring in ≤30 days"
    elif option == 'q':
        filtered = [(u,d) for u,d in items if 0 <= d <= 120]
        title = "expiring in ≤120 days"
    elif option == 'cl10':
        filtered = sorted([(u,d) for u,d in items if d>=0], key=lambda x: x[1])[:10]
        title = "10 closest"
    elif option == 'cl25':
        filtered = sorted([(u,d) for u,d in items if d>=0], key=lambda x: x[1])[:25]
        title = "25 closest"
    else:
        print("Invalid list option")
        return
    if not filtered:
        print("No users match.")
        return
    print(f"\n{title}:")
    for u, d in filtered:
        print(f"{u:20} {d} days")