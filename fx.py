# 1. Replace covpn_env.py (remove the dot)
sed -i 's/from \. import covpn_config/import covpn_config/' covpn_env.py

# 2. Do the same for other modules (just in case)
sed -i 's/from \. import covpn_config/import covpn_config/' covpn_add.py covpn_ren.py covpn_info.py

# 3. Ensure covpn.py adds /opt/covpn to sys.path (if not already)
#    Check if the line is there; if not, add it.
grep -q "sys.path.insert(0, '/opt/covpn')" covpn.py || sed -i '3i sys.path.insert(0, "/opt/covpn")' covpn.py


