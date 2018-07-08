#!/usr/bin/env python3
"""
Drive release process for connectbox images
"""

from datetime import datetime
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from github import Github


CONNECTBOX_REPOS = [
    "connectbox-pi",
    "NEO_BatteryLevelShutdown",
    "connectbox-react-icon-client",
    "access-log-analyzer",
]
# while testing
#CONNECTBOX_REPOS = ["server-services"]
GITHUB_OWNER = "ConnectBox"
#MAIN_REPO = "server-services"
MAIN_REPO = "connectbox-pi"

NEO_TYPE = "NanoPi NEO"
RPI_TYPE = "Raspberry Pi"
UNKNOWN_TYPE = "??"


def get_env_variable(var_name):
    """ Get the environment variable or return exception """
    try:
        return os.environ[var_name]
    except KeyError:
        error_msg = "Set the %s env variable" % var_name
        raise RuntimeError(error_msg)


def generate_tag_string():
    default_tag = datetime.utcnow().strftime("v%Y%m%d")
    # while testing
    # default_tag = datetime.utcnow().strftime("v%Y%m%d%H%M%S")
    tag = input("Enter tag name for this release [%s]: " % (default_tag,))
    if not tag:
        tag = default_tag

    response = input("Proceed with tag '%s'? [y/N]: " % (tag,))
    if response.lower() != "y":
        print("OK, not proceeding")
        sys.exit(0)
    return tag


def create_tags_in_repos(connectbox_org, repos, tag):
    for repo in repos:
        gh_repo = connectbox_org.get_repo(repo)
        most_recent_commit = gh_repo.get_commits()[0]
        gh_repo.create_git_tag(
            tag,
            "Automated git tag during connectbox release",
            most_recent_commit.sha,
            "commit"
        )
        # We only have a lightweight tag so far. Make it an annotated tag
        gh_repo.create_git_ref("refs/tags/%s" %
                               (tag,), most_recent_commit.sha
                              )

def create_github_release(gh_repo, tag):
    gh_repo.create_git_release(
        tag,
        tag,
        "Insert release notes here",
        draft=True,
        prerelease=True
    )


def checkout_ansible_repo(tag):
    repo = "connectbox-pi"
    if os.path.isdir(repo):
        response = input("%s directory already exists. ok to delete? [y/N]: " %
                         (repo,))
        if response.lower() != "y":
            print("OK, not proceeding")
            sys.exit(0)

        print("Deleting %s" % (repo,))
        shutil.rmtree(repo)

    repo_addr = "https://github.com/ConnectBox/connectbox-pi.git"
    subprocess.run(
        ["git", "clone", "-b", tag, "--depth=1", repo_addr],
        check=True
    )


def device_type_from_model_str(model_str):
    if NEO_TYPE in model_str:
        return NEO_TYPE
    elif RPI_TYPE in model_str:
        return RPI_TYPE

    return UNKNOWN_TYPE


def get_device_ip_and_type():
    device_addr = ""
    while not device_addr:
        response = input("Enter IP address for build device: ")
        try:
            device_addr = ipaddress.ip_address(response)
        except ValueError as val:
            print(val.args[0])
            device_addr = ""

    # We don't care about known hosts given we touch a new device each time
    known_hosts = Path("~/.ssh/known_hosts")
    known_hosts.expanduser().unlink()

    can_ssh_to_device = False
    device_type = UNKNOWN_TYPE
    while not can_ssh_to_device:
        response = input(
            "Ready to attempt passwordless ssh to %s. Enter to start: " %
            (device_addr,)
        )
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
            print(cpe.args)

    return device_addr.exploded, device_type


def create_inventory(device_ip, device_type):
    if device_type == NEO_TYPE:
        inventory_str = "%s\n" % (device_ip,)
    elif device_type == RPI_TYPE:
        inventory_str = "%s fsdfsdfd\n" % (device_ip,)
    else:
        assert "got here with DEVICE_TYPE=%s" % (device_type,)
        inventory_str = ""

    inventory_fd, inventory_name = tempfile.mkstemp()
    os.pwrite(inventory_fd, inventory_str.encode("utf-8"), 0)
    os.close(inventory_fd)
    return inventory_name


def run_ansible(inventory, tag):
    print("Run: ansible-playbook -u root -i %s site.yml "
          "-e connectbox_version=%s "
          "-e deploy_sample_content=False "
          "-e do_image_preparation=True " %
          (inventory, tag)
         )


def create_img_from_sd(tag, device_type):
    print("Attach SD card from device and confirm it appears as /dev/sdb "
          "(check dmesg)")
    img_name = "%s_%s.img" % (device_type.replace(" ", "-"), tag,)
    print("sudo /vagrant/shrink-image.sh /dev/sdb ./%s" % (img_name,))
    return img_name


def compress_img(img_name):
    print("7za a -t7z -m0=lzma -mx=9 -mfb=64 -md=32m -ms=on "
          "/vagrant/%s.7z ./%s" % (img_name, img_name))


def main():
    github_token = get_env_variable("CONNECTBOX_GITHUB_TOKEN")
    connectbox_org = Github(github_token).get_organization("ConnectBox")
    tag = generate_tag_string()
    create_tags_in_repos(connectbox_org, CONNECTBOX_REPOS, tag)
    create_github_release(connectbox_org.get_repo(MAIN_REPO), tag)
    checkout_ansible_repo(tag)
    # install packages (pip3 install -r requirements.txt)
    device_ip, device_type = get_device_ip_and_type()
    inventory_name = create_inventory(device_ip, device_type)
    run_ansible(inventory_name, tag)
    img_name = create_img_from_sd(tag, device_type)
    compress_img(img_name)
    print("Now, update release notes, inserting changelog and base image name")



if __name__ == "__main__":
    main()
