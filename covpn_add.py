#!/usr/bin/env python3
import sys
import os
import argparse

# Add installation directory to Python path
COVPN_DIR = "/opt/covpn"
if COVPN_DIR not in sys.path:
    sys.path.insert(0, COVPN_DIR)

import covpn_config
import covpn_env
import covpn_add
import covpn_ren
import covpn_info

def main():
    parser = argparse.ArgumentParser(
        prog='covpn',
        description='OpenVPN management tool',
        add_help=False
    )

    parser.add_argument('--config', help='Path to config file (default: /etc/covpn/config.json)')
    parser.add_argument('-v', '--version', action='store_true', help='Show version and exit')

    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument('-a', '--add', nargs='?', const=True, default=False,
                            help='Add users. Optionally specify username (e.g., covpn -a john)')
    mode_group.add_argument('-r', '--ren', action='store_true', help='Renew certificates (interactive or with -b)')
    mode_group.add_argument('-e', '--env', action='store_true', help='Environment management')
    mode_group.add_argument('-i', '--info', action='store_true', help='Show information')
    mode_group.add_argument('-h', '--help', action='store_true', help='Show this help message')

    parser.add_argument('-b', '--batch', nargs='+', metavar='USERNAME',
                        help='Batch usernames (for --add or --ren)')
    parser.add_argument('-l', '--list', choices=['w', 'm', 'q', 'cl10', 'cl25'],
                        help='List users by expiry (for --ren)')
    parser.add_argument('--fix', action='store_true', help='Fix environment (for --env)')
    parser.add_argument('--run', action='store_true', help='Check and fix environment (for --env)')
    parser.add_argument('-u', '--users', action='store_true', help='List all users with IPs (for --info)')
    parser.add_argument('-A', '--access', metavar='TARGET', help='Show access rules for username or IP (for --info)')

    # If no arguments, show help
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Version check
    if args.version:
        version = covpn_config.get_version()
        print(f"covpn version {version}")
        sys.exit(0)

    if args.help:
        parser.print_help()
        sys.exit(0)

    if not (args.add or args.ren or args.env or args.info):
        parser.print_help()
        sys.exit(1)

    if args.add:
        if args.list or args.fix or args.run or args.users or args.access:
            parser.error('--list, --fix, --run, --users, --access are not allowed with --add')
        cfg = covpn_config.load_config(args.config)
        if not covpn_env.check_environment(fix=False):
            print("Environment not ready. Run 'covpn -e --fix' first.")
            sys.exit(1)

        username = args.add if isinstance(args.add, str) else None

        if args.batch:
            success, failed = covpn_add.add_batch(args.batch, cfg)
            print(f"Success: {len(success)}, Failed: {len(failed)}")
            if failed:
                sys.exit(1)
        else:
            covpn_add.add_interactive(cfg, username)

    elif args.ren:
        if args.fix or args.run or args.users or args.access:
            parser.error('--fix, --run, --users, --access are not allowed with --ren')
        cfg = covpn_config.load_config(args.config)
        if args.list:
            covpn_ren.list_expirations(args.list, cfg)
        elif args.batch:
            for username in args.batch:
                covpn_ren.revoke_renew_user(username, cfg)
            print("All renewed.")
        else:
            username = input("Enter username: ").strip()
            if username:
                covpn_ren.revoke_renew_user(username, cfg)
            else:
                print("Username cannot be empty.")

    elif args.env:
        if args.list or args.batch or args.users or args.access:
            parser.error('--list, --batch, --users, --access are not allowed with --env')
        cfg = covpn_config.load_config(args.config)
        if args.fix or args.run:
            fix = args.fix or args.run
            if args.run:
                if not covpn_env.check_environment(fix=False):
                    print("Attempting to fix...")
                    covpn_env.check_environment(fix=True)
            else:
                covpn_env.check_environment(fix=fix)
        else:
            covpn_env.check_environment(fix=False)

    elif args.info:
        if args.list or args.batch or args.fix or args.run:
            parser.error('--list, --batch, --fix, --run are not allowed with --info')
        cfg = covpn_config.load_config(args.config)
        if args.users:
            covpn_info.list_users_by_ip(cfg)
        elif args.access:
            covpn_info.show_access(cfg, args.access)
        else:
            parser.error('--info requires either --users or --access')

if __name__ == '__main__':
    main()