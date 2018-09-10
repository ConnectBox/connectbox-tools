#!/usr/bin/env python2
"""
Drive release process for connectbox images
"""

from datetime import datetime
import ipaddress
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import click
from github import Github


CONNECTBOX_REPOS = [
    "connectbox-pi",
    "NEO_BatteryLevelShutdown",
    "connectbox-react-icon-client",
    "access-log-analyzer",
    "simple-offline-captive-portal",
]
# while testing
#CONNECTBOX_REPOS = ["server-services"]
GITHUB_OWNER = "ConnectBox"
#MAIN_REPO = "server-services"
MAIN_REPO = "connectbox-pi"

NEO_TYPE = "NanoPi NEO"
RPI_TYPE = "Raspberry Pi"
UNKNOWN_TYPE = "??"


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
    release = gh_repo.create_git_release(
        tag,
        tag,
        "Insert release notes here",
        draft=True,
        prerelease=True
    )
    return release


def checkout_ansible_repo(tag):
    repo = "connectbox-pi"
    if os.path.isdir(repo):
        click.confirm("%s directory already exists. ok to delete?" % (repo,),
                      abort=True)

        click.echo("Deleting %s" % (repo,))
        shutil.rmtree(repo)

    repo_addr = "https://github.com/ConnectBox/connectbox-pi.git"
    subprocess.run(
        ["git", "clone", "-b", tag, "--depth=1", repo_addr],
        check=True
    )
    return repo

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
    known_hosts = Path("~/.ssh/known_hosts").expanduser()
    if known_hosts.exists():
        known_hosts.unlink()

    can_ssh_to_device = False
    device_type = UNKNOWN_TYPE
    while not can_ssh_to_device:
        response = input(
            "Ready to attempt passwordless ssh to %s. Enter to start: " %
            (device_addr,)
        )
        try:
            # what about rpi?
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

    click.secho("Deploying to %s (type: %s)" %
                (device_addr.exploded, device_type), bold=True)
    return device_addr.exploded, device_type


def create_inventory(device_ip, device_type):
    click.secho("Creating ansible inventory", fg="blue", bold=True)
    common_args = "deploy_sample_content=False do_image_preparation=True"
    if device_type == NEO_TYPE:
        inventory_str = "%s ansible_user=root %s\n" % (device_ip, common_args)
    elif device_type == RPI_TYPE:
        inventory_str = "%s ansible_user=pi %s\n" % (device_ip, common_args)
    else:
        assert "got here with DEVICE_TYPE=%s" % (device_type,)
        inventory_str = ""

    inventory_fd, inventory_name = tempfile.mkstemp()
    os.pwrite(inventory_fd, inventory_str.encode("utf-8"), 0)
    os.close(inventory_fd)
    return inventory_name


def run_ansible(inventory, tag, repo_location):
    click.secho("Running ansible", fg="blue", bold=True)
    subprocess.run(
        ["ansible-playbook",
         "-i",
         inventory,
         "-e",
         "connectbox_version=%s" % (tag,),
         "site.yml"
        ], cwd=os.path.join(repo_location, "ansible")
    )


def create_img_from_sd(tag, device_type):
    click.secho("Attach SD card from device", fg="blue", bold=True)
    # look for sdb1$ in the last line of /proc/partitions
    # perhaps prompt?
    sd_seen_in_dmesg = False
    while not sd_seen_in_dmesg:
        sd_seen_in_dmesg = click.confirm("Has SD appeared as /dev/sdb in dmesg?")
    path_to_image = "/tmp/%s_%s.img" % (device_type.replace(" ", "-"), tag,)
    subprocess.run(
        ["sudo",
         "/vagrant/shrink-image.sh",
         "/dev/sdb",
         path_to_image
        ]
    )
    return path_to_image


def compress_img(path_to_image):
    path_to_compressed_image = os.path.join(
        "/vagrant",
        "%s.7z" % (os.path.basename(path_to_image),)
    )
    cmd = ["7za",
           "a",
           "-t7z",
           "-m0=lzma",
           "-mx=9",
           "-mfb=64",
           "-md=32m",
           "-ms=on",
           path_to_compressed_image,
           path_to_image
          ]
    subprocess.run(cmd)
    return path_to_compressed_image


@click.command()
@click.option("--github-token",
              prompt=True,
              default=lambda: os.environ.get("CONNECTBOX_GITHUB_TOKEN", ""),
              help="Github token with ConnectBox org write privs")
@click.option("--tag",
              prompt="Enter tag for this release",
              default=lambda: datetime.utcnow().strftime("v%Y%m%d"),
              help="Name of this release (also used as git tag)")
@click.option("--use-existing-tag",
              is_flag=True,
              default=False,
              help="Use an existing tag and do not tag the repos")
def main(github_token, tag, use_existing_tag):
    connectbox_org = Github(github_token).get_organization("ConnectBox")
    if not use_existing_tag:
        click.confirm("Proceed with new tag '%s'?" % (tag,), abort=True)
        create_tags_in_repos(connectbox_org, CONNECTBOX_REPOS, tag)
        gh_release = create_github_release(connectbox_org.get_repo(MAIN_REPO), tag)
    else:
        click.confirm("Proceed with existing tag '%s'?" % (tag,), abort=True)
        gh_release = connectbox_org.get_repo(MAIN_REPO).get_release(tag)

    repo_location = checkout_ansible_repo(tag)
    # install packages needed for connectbox build
    subprocess.run(
        ["pip3",
         "install",
         "-r",
         os.path.join(repo_location, "requirements.txt")
        ]
    )
    device_ip, device_type = get_device_ip_and_type()
    inventory_name = create_inventory(device_ip, device_type)
    run_ansible(inventory_name, tag, repo_location)
    img_name = create_img_from_sd(tag, device_type)
    path_to_compressed_image = compress_img(img_name)
    click.secho("Compressed image complete and located at: %s" %
                (path_to_compressed_image,))
    click.secho("Uploading to Github (may take ~1hr). Check progress in the "
                "github release page itself")
    gh_release.upload_asset(path_to_compressed_image)
    click.secho("Now, update release notes, inserting changelog and base image name")


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
