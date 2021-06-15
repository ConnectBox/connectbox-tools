# Sets root account on a base armbian device with the password "waypoint"
#  and copies public keys to the host to allow subsequent keyless logins
if [ $# -ne 1 ]; then
   echo "Usage: $0 HOST";
   exit 1;
fi
HOST=$1

# Remove hostname-centric and IP-centric entries from ssh's known hosts
gsed -i '/^'$HOST'.*/d' ~/.ssh/known_hosts;
# Only try to remove IP address if it exists, lest we delete everything from
#  .ssh/known_hosts :-\
host_ip=$(dig +short $HOST)
if [ -n "$host_ip" ]; then
  gsed -i '/^'$host_ip'.*/d' ~/.ssh/known_hosts;
fi

sleep 1;

# Forced password change
# Do not create an additional user
expect << EOF
spawn ssh -t -l root -o "StrictHostKeyChecking=accept-new" $HOST
expect "password: "
send "1234\r"
expect "(current) UNIX password: "
send "1234\r"
expect "Enter new UNIX password: " 
send "waypoint\r"
expect "Retype new UNIX password: "
send "waypoint\r"
expect "Please provide a username (eg. your forename): "
send "\003\r"
expect "closed."
exit
EOF

sleep 1;

# Allow passwordless access with current keys
# add -i <private-key-name>    if you don't use ssh-agent
# e.g. spawn ssh-copy-id -i /home/username/.ssh/id_rsa $HOST
expect << EOF
spawn ssh-copy-id root@$HOST
expect "password: "
send "waypoint\r"
expect "were added."
sleep 2
exit
EOF

# Test
echo "Testing access..."
ssh root@$HOST 'echo "Successful test"'
