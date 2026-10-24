#!/bin/bash
# Prepares a freshly flashed Armbian device for make_cb.py:
#  - does Armbian's first root login (default password 1234), sets the root
#    password to "connectbox" (override with ROOT_PW=...), picks bash as the
#    shell if asked, and skips creating a normal user (Ctrl-C at that prompt);
#  - copies this machine's public key to root@HOST for keyless logins.
# Prompts match armbian-firstlogin in Armbian 23.02 (armbian/build v23.02).
# Needs: expect, ssh-copy-id  (sudo apt install expect)
# Usage: ./setup_armbian_host.sh HOST

if [ $# -ne 1 ]; then
   echo "Usage: $0 HOST"
   exit 1
fi
HOST=$1
ROOT_PW=${ROOT_PW:-connectbox}

for tool in expect ssh-copy-id; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing '$tool'. Install it with: sudo apt install expect openssh-client"
    exit 1
  fi
done

# Forget old host keys for the name and its IPv4 address (the device is new)
ssh-keygen -R "$HOST" >/dev/null 2>&1
host_ip=$(getent ahostsv4 "$HOST" | awk 'NR==1 {print $1}')
if [ -n "$host_ip" ] && [ "$host_ip" != "$HOST" ]; then
  ssh-keygen -R "$host_ip" >/dev/null 2>&1
fi

sleep 1

# Armbian first login: Create/Repeat root password, choose shell, then abort
#  user creation with Ctrl-C ("Disabling user account creation procedure")
expect <<EOF
set timeout 60
log_user 1
spawn ssh -t -o StrictHostKeyChecking=accept-new -o PubkeyAuthentication=no -l root $HOST
expect {
  "password: " { send "1234\r" }
  timeout { puts "\n*** No SSH password prompt from $HOST"; exit 1 }
  eof     { puts "\n*** SSH to $HOST failed"; exit 1 }
}
expect {
  "Create root password: " { send "$ROOT_PW\r" }
  -re {root@[^:]*:[^#]*# $} {
    # First-login wizard already done but root still has the default password:
    #  set it here, then go straight on to copying keys.
    puts "\n*** First login already done; setting the root password"
    send "echo 'root:$ROOT_PW' | chpasswd && echo PW-SET-OK\r"
    expect {
      -re {[\r\n]PW-SET-OK} {}
      timeout { puts "\n*** chpasswd did not confirm"; exit 1 }
    }
    send "exit\r"
    expect eof
    exit 0
  }
  "password: " {
    # 1234 refused: root password probably set already; try the new one
    if {[info exists tried_new]} { puts "\n*** Neither 1234 nor the new root password works on $HOST"; exit 2 }
    set tried_new 1
    send "$ROOT_PW\r"
    exp_continue
  }
  "Permission denied (" { puts "\n*** root login refused on $HOST"; exit 2 }
  timeout { puts "\n*** No 'Create root password' prompt or shell"; exit 2 }
}
expect {
  "Repeat root password: " { send "$ROOT_PW\r" }
  timeout { puts "\n*** No 'Repeat root password' prompt"; exit 1 }
}
expect {
  "Choose default system command shell" { send "1"; exp_continue }
  "Please provide a username" { send "\003" }
  "Rejected" { puts "\n*** Root password rejected"; exit 1 }
  timeout { puts "\n*** No username prompt after setting the root password"; exit 1 }
}
expect {
  "Disabling user account creation procedure" {}
  timeout { puts "\n*** Did not see the user-creation abort message" }
}
sleep 1
send "exit\r"
expect eof
EOF
rc=$?
if [ $rc -ne 0 ]; then
  echo "First-login step failed (exit $rc); not copying keys."
  exit $rc
fi

sleep 1

# Allow passwordless access with this machine's keys
# (add -i ~/.ssh/<key>.pub to ssh-copy-id if you don't use the default key)
expect <<EOF
set timeout 60
spawn ssh-copy-id -o StrictHostKeyChecking=accept-new root@$HOST
expect {
  "password: " { send "$ROOT_PW\r"; exp_continue }
  "added" {}
  "already exist on the remote system" {}
  timeout { puts "\n*** ssh-copy-id timed out"; exit 1 }
}
expect eof
EOF

# Test
echo "Testing access..."
if ssh -o BatchMode=yes root@"$HOST" 'echo "Successful test"'; then
  exit 0
else
  echo "Keyless login to root@$HOST failed"
  exit 1
fi
