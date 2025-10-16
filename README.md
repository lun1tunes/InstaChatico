To avoid redis warning at the host system apply:
echo "vm.overcommit_memory = 1" | sudo tee -a /etc/sysctl.conf && sudo sysctl -p

Verify the change:
cat /proc/sys/vm/overcommit_memory
# Should output: 1