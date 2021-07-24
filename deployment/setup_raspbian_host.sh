# Sets root account on a base raspbian-lite device with the password "connectbox"
#  and copies public keys to the host to allow subsequent keyless logins
# Also disables pi account
if [ $# -ne 1 ]; then
   echo "Usage: $0 HOST";
   exit 1;
fi
HOST=$1

# Remove hostname-centric and IP-centric entries from ssh's known hosts
sed -i '/^'$HOST'.*/d' ~/.ssh/known_hosts;
# Only try to remove IP address if it exists, lest we delete everything from
#  .ssh/known_hosts :-\
host_ip=$(dig +short $HOST)
if [ -n "$host_ip" ]; then
  sed -i '/^'$host_ip'.*/d' ~/.ssh/known_hosts;
fi

sleep 1;

# Enable root logins
# Set root password
expect << EOF
spawn ssh -t -l pi -o "StrictHostKeyChecking=accept-new" $HOST
expect "password: "
send "raspberry\r"
expect "pi@rpi3:~ $ "
send "sudo sed -i 's/^#PermitRootLogin.*/PermitRootLogin=yes/' /etc/ssh/sshd_config\r"
expect "pi@rpi3:~ $ "
send "sudo systemctl restart ssh\r"
expect "pi@rpi3:~ $ "
send "sudo passwd\r"
expect "Enter new UNIX password: "
send "connectbox\r"
expect "Retype new UNIX password: "
send "connectbox\r"
expect "pi@rpi3:~ $ "
send "exit\r"
exit
EOF

sleep 1;

# Allow passwordless access with current keys
# add -i <private-key-name>    if you don't use ssh-agent
# e.g. spawn ssh-copy-id -i /home/username/.ssh/id_rsa $HOST
expect << EOF
spawn ssh-copy-id root@$HOST
expect "password: "
send "connectbox\r"
expect "were added."
sleep 2
exit
EOF

echo "locking the pi account"
ssh root@$HOST "usermod --lock pi"

# Test
echo "Testing access..."
ssh root@$HOST 'echo "Successful test"'
