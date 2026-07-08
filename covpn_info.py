import os
import subprocess
import glob
from . import covpn_config

def list_users_by_ip(cfg):
    ccd_dir = cfg['server']['ccd_dir']
    files = glob.glob(os.path.join(ccd_dir, '*'))
    users = []
    for f in files:
        username = os.path.basename(f)
        try:
            with open(f, 'r') as fp:
                for line in fp:
                    if line.startswith('ifconfig-push'):
                        parts = line.split()
                        ip = parts[1]
                        users.append((username, ip))
                        break
        except:
            continue
    users.sort(key=lambda x: int(x[1].split('.')[-1]))
    print("Username          IP")
    for u, ip in users:
        print(f"{u:<18} {ip}")

def show_access(cfg, target):
    # Determine if target is IP or username
    if re.match(r'^\d+\.\d+\.\d+\.\d+$', target):
        # IP
        ip = target
    else:
        # username – find its IP from CCD
        ccd_path = os.path.join(cfg['server']['ccd_dir'], target)
        if not os.path.exists(ccd_path):
            print(f"User {target} not found.")
            return
        with open(ccd_path, 'r') as f:
            for line in f:
                if line.startswith('ifconfig-push'):
                    ip = line.split()[1]
                    break
            else:
                print("Could not determine IP for this user.")
                return
    # Now show iptables rules for this IP and subnet
    subnet = cfg['server']['vpn_subnet'] + '/24'
    print(f"Access rules for IP {ip} (including subnet {subnet}):")
    # Use iptables -L -n | grep <ip> etc.
    # For simplicity, we'll show a raw output
    subprocess.run(['iptables', '-L', '-n'] | grep -E f"{ip}|{subnet}", shell=True)