# Sets root account on a base armbian device with the password "connectbox"
#  and copies public keys to the host to allow subsequent keyless logins
if [ $# -ne 1 ]; then
   echo "Usage: $0 HOST";
   exit 1;
fi
HOST=$1

# Remove hostname-centric and IP-centric entries from ssh's known hosts
gsed -i '/^'$HOST'.*/d' ~/.ssh/known_hosts;
gsed -i '/^'$(dig +short $HOST)'.*/d' ~/.ssh/known_hosts;

sleep 1;

# Forced password change
# Do not create an additional user
expect << EOF
spawn ssh -t -o "StrictHostKeyChecking=accept-new" $HOST
expect "password: "
send "1234\r"
expect "(current) UNIX password: "
send "1234\r"
expect "Enter new UNIX password: " 
send "connectbox\r"
expect "Retype new UNIX password: "
send "connectbox\r"
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
spawn ssh-copy-id $HOST
expect "password: "
send "connectbox\r"
expect "were added."
sleep 2
exit
EOF

# Test
echo "Testing access..."
ssh $HOST 'echo "Successful test"'