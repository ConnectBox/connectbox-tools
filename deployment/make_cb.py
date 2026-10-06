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
import shlex
import tempfile
import click


CONNECTBOX_REPOS = [
    "connectbox-pi",
    "connectbox-hat-service",
    "connectbox-react-icon-client",
    "connectbox-access-log-analyzer",
    "simple-offline-captive-portal",
    "connectbox-wifi-configurator",
]
# while testing
GITHUB_OWNER = "ConnectBox"
MAIN_REPO = "connectbox-pi"

NEO_TYPE = "NanoPi NEO"
RPI_TYPE = "Raspberry Pi"
OPI_TYPE = "OrangePi Zero2"
UNKNOWN_TYPE = "?? "

def checkout_ansible_repo(branch="master"):
    """
    Fresh shallow clone of connectbox-pi at `branch` (or tag) into ./connectbox-pi.
    (The old version ran "cd" through os.system, which has no effect on this
    process, and "git checkout -B" in the wrong directory, so the branch asked
    for was never built.)
    """
    repo = "connectbox-pi"
    click.secho("Deleting any previous %s build directory" % (repo,),
                fg="blue", bold=True)

    if os.path.exists(repo):
        shutil.rmtree(repo)

    repo_addr = "https://github.com/ConnectBox/connectbox-pi.git"
    subprocess.run(
        ["git", "clone", "--depth=1", "--branch", branch, repo_addr],
        check=True
    )
    return repo


def install_ansible_requirements(repo_location):
    """
    pip-install connectbox-pi's requirements only when Ansible is missing.
    On Raspberry Pi OS Bookworm Ansible comes from apt and a system-wide pip
    install is refused (externally managed environment).
    """
    if shutil.which("ansible-playbook"):
        return
    subprocess.run(
        ["pip3", "install", "--user", "-r",
         os.path.join(repo_location, "requirements.txt")]
    )


def device_type_from_model_str(model_str):
    if NEO_TYPE in model_str:
        return NEO_TYPE

    if RPI_TYPE in model_str:
        return RPI_TYPE

    if OPI_TYPE in model_str:
        return OPI_TYPE

    return UNKNOWN_TYPE + model_str.strip("\x00 \n")


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


THE_WELL_OPTIONS = ["-e", "connectbox_default_hostname=TheWell",
                    "-e", "wireless_country_code=US",
                    "-e", "lcd_logo=lcdwell_logo.png"]


def build_options():
    """
    Ask for The Well branding or other ansible-playbook options and return
    them as a list of separate arguments.  Options are typed the way they
    would be on the command line, e.g.  -e wireless_country_code=AU -v
    (commas between options, as the old prompt asked for, are also accepted).
    """
    answer = click.prompt(click.style("Do you want to build TheWell? (y/n):",
                                      fg="white", bold=True),
                          type=str, default="n")
    if answer.strip().lower() in ("y", "yes"):
        return list(THE_WELL_OPTIONS)
    extra = click.prompt(click.style("Enter other build options (e.g. -e wireless_country_code=AU)",
                                     fg="white", bold=True),
                         type=str, default="", show_default=False)
    # a trailing comma on an argument is a separator, not part of a value
    return [arg.rstrip(",") for arg in shlex.split(extra) if arg.rstrip(",")]


def run_ansible(inventory, tag, repo_location):
    """
    Run site.yml from connectbox-pi/ansible so that ansible/ansible.cfg
    (force_handlers, pipelining) applies - it is only read from the current
    directory.  Release builds always run as root, even on Raspberry Pi OS
    (the ansible_user here overrides group_vars/raspbian).
    """
    cmd = (["ansible-playbook"] + build_options() +
           ["-i", inventory,
            "-e", "ansible_user=root",
            "-e", "connectbox_version=%s" % (tag,),
            "-e", "ansible_python_interpreter=/usr/bin/python3",
            "site.yml"])
    ansible_dir = os.path.join(os.path.abspath(repo_location), "ansible")
    click.secho("running in %s: %s" % (ansible_dir, " ".join(shlex.quote(c) for c in cmd)),
                fg="blue", bold=True)
    subprocess.run(cmd, cwd=ansible_dir)


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
        text = click.style("Enter branch or tag to build",
                           fg="blue", bold=True)
        response = click.prompt(text, default="master")
        repo_location = checkout_ansible_repo(response)

    # install packages needed for connectbox build (only if Ansible is missing)
    install_ansible_requirements(repo_location)

    inventory_name = create_inventory(device_ip)
    run_ansible(inventory_name, tag, repo_location)

if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
