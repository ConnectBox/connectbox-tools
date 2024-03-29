#!/usr/bin/env python3
"""
Create local connectbox image

"""

from datetime import datetime
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import click


CONNECTBOX_REPOS = [
    "connectbox-pi",
    "connectbox-hat-service",
    "connectbox-react-icon-client",
    "access-log-analyzer",
    "simple-offline-captive-portal",
    "wifi-configurator",
]
# while testing
GITHUB_OWNER = "ConnectBox"
MAIN_REPO = "connectbox-pi"

NEO_TYPE = "NanoPi NEO"
RPI_TYPE = "Raspberry Pi"
OPI_TYPE = "OrangePi Zero2"
UNKNOWN_TYPE = "?? "

def checkout_ansible_repo(branch="main"):
    repo = "connectbox-pi"
    click.secho("Deleting any previous %s build directory" % (repo,),
                fg="blue", bold=True)

    if os.path.exists(repo):
        shutil.rmtree(repo)

    repo_addr = "https://github.com/ConnectBox/connectbox-pi.git"
    subprocess.run(
        ["git", "clone", "--depth=1", repo_addr],
        check=True
    )
    os.system('cd connectbox-pi' )
    os.system("git checkout -B "+str(branch))
    os.system('cd ../')
    return repo


def device_type_from_model_str(model_str):
    if NEO_TYPE in model_str:
        return NEO_TYPE

    if RPI_TYPE in model_str:
        return RPI_TYPE

    if OPI_TYPE in model_str:
        return OPI_TYPE

    return UNKNOWN_TYPE+"{{ model_str }}"


def get_device_ip_and_type():
    device_addr = ""
    while not device_addr:
        text = click.style("Enter IP address for build device",
                           fg="blue", bold=True)
        response = click.prompt(text)
        try:
            device_addr = ipaddress.ip_address(response)
        except ValueError as val:
            click.secho(val.args[0], fg="blue", bold=True)
            device_addr = ""

    # We don't care about known hosts given we touch a new device each time
    known_hosts = Path("~/.ssh/known_hosts").expanduser()
    if known_hosts.exists():
        known_hosts.unlink()

    can_ssh_to_device = False
    device_type = UNKNOWN_TYPE
    while not can_ssh_to_device:
        click.secho("Ready to attempt passwordless ssh to %s" % (device_addr,),
                    fg="blue", bold=True)
#        click.pause()
        try:
            proc = subprocess.run([
                "ssh",
                "-oStrictHostKeyChecking=no",
                "-l",
                "root",
                device_addr.exploded,
                "cat /sys/firmware/devicetree/base/model"
                ], check=True, stdout=subprocess.PIPE)
            device_type = \
                device_type_from_model_str(proc.stdout.decode("utf-8"))
            can_ssh_to_device = True
        except subprocess.CalledProcessError as cpe:
            click.secho(cpe.args, fg="blue", bold=True)

    click.secho("Deploying to %s (type: %s)" %
                (device_addr.exploded, device_type), bold=True)
    return device_addr.exploded, device_type


def create_inventory(device_ip):
    click.secho("Creating ansible inventory", fg="blue", bold=True)
    inventory_str = \
        "%s deploy_sample_content=False do_image_preparation=True\n" % \
        (device_ip,)
    inventory_fd, inventory_name = tempfile.mkstemp()

    os.pwrite(inventory_fd, inventory_str.encode("utf-8"), 0)
    os.close(inventory_fd)
    return inventory_name


def run_ansible(inventory, tag, repo_location):
    # release builds always run with the root account, even on raspbian.
    # the ansible_user here overrides the group_vars/raspbian variables
    a = click.style("Do you want to build TheWell? (y/n):",
                           fg="white", bold=True)
    a = click.prompt(a, type=str, default="n")
    if a in ("y", "Y", "yes", "Yes"):
        a = '-e connectbox_default_hostname=TheWell -e wireless_country_code=US, -e build_moodle=true, -e lcd_logo=lcdwell_logo.png'
    else:
        a = click.style("Enter other build options (separated by , )",
                           fg="white", bold=True)
        a = click.prompt(a, type=str,default="")
        if a == "":
           a = '-v'
        else:
           a = a.lstrip(' ')
           b = len(a)
           if b>2:
               if a[b-1] == ",":
                   a = a[0:b-2]

    click.secho('running: "ansible-playbook", '+ a +', "-u","root", "-i", "inventory", "-e", "ansible_user=root", "-e", "connectbox_version=%s" % (tag,), "-e", "ansible-python-interpreter=/usr/bin/python3", site.yml')
    subprocess.run(
         ["ansible-playbook",
          "%s" % (a,),
          "-i",
          inventory,
          "-e",
          "ansible_user=root",
          "-e",
          "connectbox_version=%s" % (tag,),
          "-e",
          "ansible_python_interpreter=/usr/bin/python3",
          "connectbox-pi/ansible/site.yml"
            ]              # close out the ansible script here you must be in the ansible directory.
#           ], cwd=os.path.join(repo_location, "ansible")
    )


# The following is required to enable the @click commands to run at beginning
#  (before main)
@click.command()
@click.option("--update_ansible",
              prompt="Update ansible scripts and code modules (y/N)",
              default="N",
              help="Update ansible flag")

@click.option("--tag",
              prompt="Enter tag for this release",
              default=lambda: datetime.utcnow().strftime("v%Y%m%d"),
              help="Name of this release")

def main(tag, update_ansible):
    device_ip, device_type = get_device_ip_and_type()
    #set default repo_location
    repo_location = "connectbox-pi"

    # If the ansible path doesn't exist, then update_ansible 
    ansible_path = Path(os.getcwd() + "/connectbox-pi/ansible").expanduser()
    print("ansible_path",ansible_path)
    if not ansible_path.exists():
        update_ansible = "Y"


    if update_ansible == "Y" or update_ansible == "y":
        text = click.style("Enter branch to build (main)",
                           fg="blue", bold=True)
        response = click.prompt(text)
        if response == "":
            response = "main"
        repo_location = checkout_ansible_repo(response)

    # install packages needed for connectbox build
        subprocess.run(
            ["pip3",
             "install",
             "-r",
                os.path.join(repo_location, "requirements.txt")
             ]
        )
    os.system('cd '+str(ansible_path))

    inventory_name = create_inventory(device_ip)
    run_ansible(inventory_name, tag, repo_location)
    orig_path=str(ansible_path)[0:(str(ansible_path).find(repo_location)-1)]
    os.system('cd '+orig_path)

if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
